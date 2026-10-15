"""Persistência do CaseLab.

Usa SQLAlchemy para funcionar tanto com SQLite (demonstração local) quanto com
PostgreSQL (produção: Supabase, Neon, Azure Database...). Basta definir DATABASE_URL.
Todas as consultas são parametrizadas pelo SQLAlchemy (proteção contra SQL injection).
"""
import json
import os
from datetime import date, datetime

import streamlit as st
from sqlalchemy import (
    Boolean, Column, Integer, MetaData, String, Table, Text,
    create_engine, delete, func, insert, or_, select, update,
)

from . import config

metadata = MetaData()

STATUS_TRILHA = {
    "rascunho": "📝 Rascunho",
    "em_revisao": "🔎 Em revisão pela T&D",
    "aprovada": "✅ Aprovada",
    "publicada": "🟢 Publicada",
    "encerrada": "⏹️ Encerrada",
}

# Encaminhamento de cada ideia, definido pelo gestor
STATUS_IDEIA = {
    "nova": "🆕 Nova",
    "em_conversa": "💬 Em conversa",
    "selecionada": "🧪 Selecionada para teste",
    "implementada": "✅ Implementada",
    "guardada": "📦 Guardada para depois",
}

materiais = Table(
    "materiais", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nome", String(200), nullable=False),
    Column("descricao", Text),
    Column("conteudo", Text, nullable=False),
    Column("criado_por", String(200)),
    Column("criado_em", String(32)),
)

trilhas = Table(
    "trilhas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("status", String(20), nullable=False, default="rascunho"),
    # 1. O problema, 2. quem, 3. com quais competências, 4. com quais materiais
    Column("problema", Text),
    Column("publico", String(300)),
    Column("contexto_equipe", Text),
    Column("competencias", Text),          # JSON: lista de competências necessárias
    Column("materiais_ids", Text),         # JSON: ids da biblioteca
    # Trilha gerada e revisada
    Column("titulo", String(300)),
    Column("caso", Text),
    Column("pergunta", Text),
    Column("entrega", Text),               # entrega esperada, definida junto com o caso
    Column("etapas", Text),                # JSON: etapas de desenvolvimento
    Column("trechos", Text),               # JSON: trechos do material usados como base
    Column("gerado_sem_material", Boolean, default=False),
    Column("limite_chars", Integer, default=3000),
    Column("max_versoes", Integer, default=2),
    Column("bloquear_colar", Boolean, default=True),
    Column("prazo", String(10)),
    Column("nota_revisao", Text),          # observações da área de T&D
    # Fechamento
    Column("sintese", Text),
    Column("devolutiva", Text),            # devolutiva coletiva do gestor
    Column("devolutiva_em", String(32)),
    # Rastreabilidade
    Column("criado_por", String(200)),
    Column("criado_em", String(32)),
    Column("enviado_revisao_em", String(32)),
    Column("aprovado_por", String(200)),
    Column("aprovado_em", String(32)),
    Column("publicado_em", String(32)),
)

progresso = Table(
    "progresso", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trilha_id", Integer, nullable=False, index=True),
    Column("participante_id", String(200), nullable=False, index=True),
    Column("participante_nome", String(200)),
    Column("etapa", Integer, nullable=False),
    Column("reflexao", Text),
    Column("concluida_em", String(32)),
)

propostas = Table(
    "propostas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trilha_id", Integer, nullable=False, index=True),
    Column("participante_id", String(200), nullable=False, index=True),
    Column("participante_nome", String(200)),
    Column("versao", Integer, nullable=False),
    Column("leitura", Text, nullable=False),     # a leitura do participante sobre o problema
    Column("proposta", Text, nullable=False),
    Column("resposta_provocacao", Text),
    Column("feedback", Text),                    # JSON da mentoria
    Column("tempo_segundos", Integer),
    Column("ritmo_atipico", Boolean, default=False),
    Column("status_ideia", String(20), default="nova"),
    Column("criado_em", String(32)),
)

comentarios = Table(
    "comentarios", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trilha_id", Integer, nullable=False, index=True),
    Column("alvo_id", String(200), nullable=False),   # dono da proposta comentada
    Column("autor_id", String(200), nullable=False),
    Column("autor_nome", String(200)),
    Column("texto", Text, nullable=False),
    Column("criado_em", String(32)),
)

auditoria = Table(
    "auditoria", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("quando", String(32)),
    Column("usuario", String(200)),
    Column("acao", String(60)),
    Column("detalhe", Text),
)

_JSON_TRILHA = {"competencias": list, "materiais_ids": list, "etapas": list, "trechos": list}


@st.cache_resource(show_spinner=False)
def _engine():
    url = config.DATABASE_URL
    if url:
        url = str(url)
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return create_engine(url, pool_pre_ping=True)
    caminho = os.path.join(config.RAIZ, "caselab.db")
    return create_engine(f"sqlite:///{caminho}", connect_args={"check_same_thread": False})


@st.cache_resource(show_spinner=False)
def init():
    metadata.create_all(_engine())
    return True


# --- Datas ---
def agora() -> str:
    return datetime.now(config.FUSO).strftime("%Y-%m-%d %H:%M:%S")


def hoje() -> date:
    return datetime.now(config.FUSO).date()


def data_br(valor) -> str:
    if not valor:
        return ""
    try:
        texto = str(valor)
        convertido = date.fromisoformat(texto[:10]).strftime("%d/%m/%Y")
        return convertido + (f" {texto[11:16]}" if len(texto) > 10 else "")
    except ValueError:
        return str(valor)


# --- Execução ---
def _inserir(tabela, valores: dict) -> int:
    with _engine().begin() as conn:
        return conn.execute(insert(tabela).values(**valores)).inserted_primary_key[0]


def _linhas(consulta) -> list[dict]:
    with _engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(consulta)]


def _executar(comando) -> int:
    with _engine().begin() as conn:
        return conn.execute(comando).rowcount or 0


# --- Biblioteca de materiais ---
def criar_material(nome, descricao, conteudo, autor) -> int:
    return _inserir(materiais, dict(nome=nome, descricao=descricao, conteudo=conteudo,
                                    criado_por=autor, criado_em=agora()))


def listar_materiais() -> list[dict]:
    m = materiais.c
    return _linhas(select(m.id, m.nome, m.descricao, m.criado_por, m.criado_em,
                          func.length(m.conteudo).label("tamanho")).order_by(m.nome))


def obter_material(mid) -> dict | None:
    linhas = _linhas(select(materiais).where(materiais.c.id == mid))
    return linhas[0] if linhas else None


def excluir_material(mid) -> None:
    _executar(delete(materiais).where(materiais.c.id == mid))


# --- Trilhas ---
def _codificar(valores: dict) -> dict:
    v = dict(valores)
    for campo in _JSON_TRILHA:
        if campo in v and v[campo] is not None and not isinstance(v[campo], str):
            v[campo] = json.dumps(v[campo], ensure_ascii=False)
    return v


def _decodificar(t: dict) -> dict:
    for campo, tipo in _JSON_TRILHA.items():
        try:
            t[campo] = json.loads(t[campo]) if t.get(campo) else tipo()
        except (TypeError, json.JSONDecodeError):
            t[campo] = tipo()
    return t


def criar_trilha(valores: dict) -> int:
    v = _codificar(valores)
    v.setdefault("status", "rascunho")
    v["criado_em"] = agora()
    return _inserir(trilhas, v)


def atualizar_trilha(tid, valores: dict) -> None:
    _executar(update(trilhas).where(trilhas.c.id == tid).values(**_codificar(valores)))


def obter_trilha(tid) -> dict | None:
    linhas = _linhas(select(trilhas).where(trilhas.c.id == tid))
    return _decodificar(linhas[0]) if linhas else None


def listar_trilhas(status: list[str] | None = None) -> list[dict]:
    t = trilhas.c
    consulta = select(t.id, t.titulo, t.status, t.publico, t.prazo, t.criado_por, t.criado_em,
                      t.publicado_em, t.devolutiva_em).order_by(t.id.desc())
    if status:
        consulta = consulta.where(t.status.in_(status))
    return _linhas(consulta)


def excluir_trilha(tid) -> None:
    _executar(delete(trilhas).where(trilhas.c.id == tid))


def prazo_vencido(trilha: dict) -> bool:
    if not trilha.get("prazo"):
        return False
    try:
        return date.fromisoformat(trilha["prazo"]) < hoje()
    except ValueError:
        return False


# --- Progresso nas etapas ---
def concluir_etapa(tid, pid, nome, etapa: int, reflexao: str) -> None:
    p = progresso.c
    existente = _linhas(select(p.id).where(p.trilha_id == tid, p.participante_id == pid, p.etapa == etapa))
    if existente:
        _executar(update(progresso).where(p.id == existente[0]["id"]).values(reflexao=reflexao, concluida_em=agora()))
    else:
        _inserir(progresso, dict(trilha_id=tid, participante_id=pid, participante_nome=nome,
                                 etapa=etapa, reflexao=reflexao, concluida_em=agora()))


def progresso_participante(tid, pid) -> dict[int, dict]:
    p = progresso.c
    linhas = _linhas(select(progresso).where(p.trilha_id == tid, p.participante_id == pid))
    return {r["etapa"]: r for r in linhas}


def progresso_trilha(tid) -> list[dict]:
    p = progresso.c
    return _linhas(select(progresso).where(p.trilha_id == tid).order_by(p.participante_id, p.etapa))


# --- Propostas ---
def _proposta(r: dict) -> dict:
    try:
        r["feedback"] = json.loads(r["feedback"]) if r.get("feedback") else {}
    except (TypeError, json.JSONDecodeError):
        r["feedback"] = {}
    return r


def registrar_proposta(valores: dict) -> int:
    v = dict(valores)
    if isinstance(v.get("feedback"), (dict, list)):
        v["feedback"] = json.dumps(v["feedback"], ensure_ascii=False)
    v["criado_em"] = agora()
    return _inserir(propostas, v)


def propostas_participante(tid, pid) -> list[dict]:
    p = propostas.c
    linhas = _linhas(select(propostas).where(p.trilha_id == tid, p.participante_id == pid).order_by(p.versao))
    return [_proposta(x) for x in linhas]


def listar_propostas(tid) -> list[dict]:
    p = propostas.c
    linhas = _linhas(select(propostas).where(p.trilha_id == tid).order_by(p.participante_id, p.versao))
    return [_proposta(x) for x in linhas]


def propostas_atuais(tid) -> list[dict]:
    """A versão mais recente da proposta de cada participante."""
    atuais: dict[str, dict] = {}
    for p in listar_propostas(tid):
        atuais[p["participante_id"]] = p
    return list(atuais.values())


def contar_mentorias_hoje(pid) -> int:
    p = propostas.c
    linhas = _linhas(select(func.count().label("n"))
                     .where(p.participante_id == pid, p.criado_em.like(f"{hoje().isoformat()}%")))
    return int(linhas[0]["n"]) if linhas else 0


def atualizar_status_ideia(tid, pid, status: str) -> None:
    if status in STATUS_IDEIA:
        p = propostas.c
        _executar(update(propostas).where(p.trilha_id == tid, p.participante_id == pid).values(status_ideia=status))


# --- Mural: comentários ---
def comentar(tid, alvo_id, autor_id, autor_nome, texto) -> int:
    return _inserir(comentarios, dict(trilha_id=tid, alvo_id=alvo_id, autor_id=autor_id,
                                      autor_nome=autor_nome, texto=texto, criado_em=agora()))


def listar_comentarios(tid) -> list[dict]:
    c = comentarios.c
    return _linhas(select(comentarios).where(c.trilha_id == tid).order_by(c.id))


# --- LGPD ---
def participantes() -> list[dict]:
    nomes: dict[str, dict] = {}
    for tabela in (progresso, propostas):
        c = tabela.c
        for r in _linhas(select(c.participante_id, func.max(c.participante_nome).label("nome"))
                         .group_by(c.participante_id)):
            nomes.setdefault(r["participante_id"], {"participante_id": r["participante_id"], "nome": r["nome"]})
    c = comentarios.c
    for r in _linhas(select(c.autor_id, func.max(c.autor_nome).label("nome")).group_by(c.autor_id)):
        nomes.setdefault(r["autor_id"], {"participante_id": r["autor_id"], "nome": r["nome"]})
    return sorted(nomes.values(), key=lambda x: (x["nome"] or "").lower())


def excluir_dados_participante(pid) -> int:
    total = _executar(delete(progresso).where(progresso.c.participante_id == pid))
    total += _executar(delete(propostas).where(propostas.c.participante_id == pid))
    c = comentarios.c
    total += _executar(delete(comentarios).where(or_(c.autor_id == pid, c.alvo_id == pid)))
    return total


# --- Auditoria ---
def auditar(usuario, acao: str, detalhe: str = "") -> None:
    try:
        _inserir(auditoria, dict(quando=agora(), usuario=str(usuario or "anônimo")[:200],
                                 acao=acao[:60], detalhe=str(detalhe)[:1000]))
    except Exception:
        pass  # A auditoria nunca deve derrubar a aplicação
