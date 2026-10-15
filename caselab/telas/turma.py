"""Gestor: acompanhar a turma, ler a síntese, encaminhar ideias e dar a devolutiva coletiva."""
from collections import Counter

import pandas as pd
import streamlit as st

from caselab import config, db, ia, seguranca, teams
from caselab.seguranca import md
from caselab.telas import colaborador


def _gestor() -> bool:
    return bool(st.session_state.get("usuario", {}).get("gestor"))


def pagina() -> None:
    seguranca.exigir("gestor", "td")
    st.title("👥 Acompanhar a turma")
    st.markdown("Veja como a turma avança, o que ela propôs e feche a trilha com uma devolutiva coletiva — "
                "sem precisar responder pessoa por pessoa.")
    aviso = st.session_state.pop("aviso_turma", None)
    if aviso:
        getattr(st, aviso[0])(aviso[1])

    lista = db.listar_trilhas(status=["publicada", "encerrada"])
    if not lista:
        st.info("Nenhuma trilha publicada ainda.")
        _privacidade()
        return
    rotulos = {t["id"]: f"{db.STATUS_TRILHA.get(t['status'], t['status'])} · #{t['id']} · {t['titulo']}" for t in lista}
    tid = st.selectbox("Trilha", list(rotulos), format_func=rotulos.get)
    t = db.obter_trilha(tid)

    progresso = db.progresso_trilha(tid)
    propostas = db.propostas_atuais(tid)
    comentarios = db.listar_comentarios(tid)

    abas = st.tabs(["📈 Andamento", "💡 Propostas", "🧠 Síntese e devolutiva", "📥 Exportar"])
    with abas[0]:
        _andamento(t, progresso, propostas, comentarios)
    with abas[1]:
        _propostas(t, propostas, comentarios)
    with abas[2]:
        _sintese_devolutiva(t, propostas, comentarios, progresso)
    with abas[3]:
        _exportar(t, progresso, comentarios)
    _privacidade()


def _andamento(t: dict, progresso: list[dict], propostas: list[dict], comentarios: list[dict]) -> None:
    participantes = {r["participante_id"] for r in progresso} | {p["participante_id"] for p in propostas}
    total_etapas = len(t["etapas"])
    concluiram = Counter(r["participante_id"] for r in progresso)
    todas = sum(1 for n in concluiram.values() if n >= total_etapas)
    selecionadas = sum(1 for p in propostas if p.get("status_ideia") in ("selecionada", "implementada"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Participantes", len(participantes))
    c2.metric("Concluíram as etapas", todas)
    c3.metric("Propostas no mural", len(propostas), help=f"{len(comentarios)} comentários entre colegas")
    c4.metric("Ideias selecionadas", selecionadas)
    if not participantes:
        st.info("Ninguém começou a trilha ainda.")
        return

    st.markdown("#### Quantas pessoas concluíram cada etapa")
    por_etapa = Counter(r["etapa"] for r in progresso)
    nomes = [f"{i + 1}. {e['titulo']}" for i, e in enumerate(t["etapas"])] + ["Proposta enviada"]
    valores = [por_etapa.get(i, 0) for i in range(total_etapas)] + [len(propostas)]
    st.bar_chart(pd.DataFrame({"Pessoas": valores}, index=pd.Index(nomes, name="Etapa")),
                 horizontal=True, x_label="Pessoas", y_label="")

    if propostas:
        st.markdown("#### Competências mobilizadas nas propostas")
        competencias = [c.split(":", 1)[0].strip() for c in t["competencias"]]
        contagem = Counter(c for p in propostas for c in p["feedback"].get("competencias_aplicadas", []))
        st.bar_chart(pd.DataFrame({"Propostas": [contagem.get(c, 0) for c in competencias]},
                                  index=pd.Index(competencias, name="Competência")),
                     horizontal=True, x_label="Propostas", y_label="")
        faltam = [c for c in competencias if not contagem.get(c)]
        if faltam:
            st.caption("Ainda não apareceram nas propostas: " + ", ".join(faltam) +
                       ". Pode valer um reforço com a área de T&D.")


def _alterar_status(tid: int, pid: str, chave: str) -> None:
    db.atualizar_status_ideia(tid, pid, st.session_state[chave])
    db.auditar(seguranca.autor_atual(), "status_ideia_alterado", f"trilha={tid} status={st.session_state[chave]}")


def _propostas(t: dict, propostas: list[dict], comentarios: list[dict]) -> None:
    if not propostas:
        st.info("Nenhuma proposta enviada ainda.")
        return
    st.caption("Marque o encaminhamento das ideias. As selecionadas aparecem para cada autor junto com a devolutiva coletiva.")
    por_alvo = Counter(c["alvo_id"] for c in comentarios)
    filtro = st.multiselect("Filtrar por encaminhamento", list(db.STATUS_IDEIA), format_func=db.STATUS_IDEIA.get)
    for p in propostas:
        status = p.get("status_ideia") or "nova"
        if filtro and status not in filtro:
            continue
        resumo = p["feedback"].get("sintese") or p["proposta"][:100]
        with st.expander(f"{db.STATUS_IDEIA.get(status, status)} · {p['participante_nome']} — {resumo} · 💬 {por_alvo.get(p['participante_id'], 0)}"):
            st.caption(f"Versão {p['versao']} · {db.data_br(p['criado_em'])}"
                       + (" · ⏱️ ritmo de escrita acima do esperado" if p["ritmo_atipico"] else ""))
            colaborador.mostrar_proposta(p)
            with st.popover("Ver mentoria da IA"):
                colaborador.mostrar_mentoria(p["feedback"])
            if _gestor():
                chave = f"status_{t['id']}_{p['participante_id']}"
                opcoes = list(db.STATUS_IDEIA)
                st.selectbox("Encaminhamento", opcoes, index=opcoes.index(status) if status in opcoes else 0,
                             format_func=db.STATUS_IDEIA.get, key=chave,
                             on_change=_alterar_status, args=(t["id"], p["participante_id"], chave))


def _sintese_devolutiva(t: dict, propostas: list[dict], comentarios: list[dict], progresso: list[dict]) -> None:
    st.markdown("#### 🧠 Síntese da turma")
    if t.get("sintese"):
        with st.container(border=True):
            st.markdown(md(t["sintese"]))
    else:
        st.caption("A IA lê as propostas, os comentários e as reflexões (sem nomes) e organiza o que a turma produziu, "
                   "além de sugerir um rascunho de devolutiva coletiva.")
    if propostas and st.button("Atualizar síntese" if t.get("sintese") else "Gerar síntese da turma"):
        por_alvo = Counter(c["alvo_id"] for c in comentarios)
        dados = [{**p, "n_comentarios": por_alvo.get(p["participante_id"], 0)} for p in propostas]
        with st.spinner("Organizando o que a turma produziu..."):
            try:
                resultado = ia.sintese_turma(t, dados, [c["texto"] for c in comentarios],
                                             [r["reflexao"] for r in progresso if r.get("reflexao")])
            except ia.ErroIA as erro:
                st.error(str(erro))
                return
        db.atualizar_trilha(t["id"], {"sintese": resultado["sintese"]})
        if resultado["rascunho_devolutiva"] and not t.get("devolutiva"):
            st.session_state[f"devolutiva_{t['id']}"] = resultado["rascunho_devolutiva"]
        db.auditar(seguranca.autor_atual(), "sintese_gerada", f"trilha={t['id']}")
        st.rerun()
    if not propostas:
        st.info("A síntese fica disponível quando houver propostas.")

    st.markdown("#### 📣 Devolutiva coletiva")
    if not _gestor():
        st.markdown(md(t.get("devolutiva")) if t.get("devolutiva") else "A devolutiva é escrita pelo gestor.")
        return
    st.caption("Uma única mensagem para a turma: reconheça o que foi construído, conte quais ideias serão exploradas "
               "e combine os próximos passos. Cada autor vê, junto, o encaminhamento da própria ideia.")
    chave = f"devolutiva_{t['id']}"
    st.session_state.setdefault(chave, t.get("devolutiva") or "")
    texto = st.text_area("Devolutiva para a turma", key=chave, height=220, max_chars=4000,
                         placeholder="Gere a síntese para receber um rascunho, ou escreva com as suas palavras.")
    canais = config.canais_teams()
    opcoes = ["Não avisar no Teams"] + list(canais)
    canal = st.selectbox("Avisar a turma no canal do Teams", opcoes, key=f"canal_devolutiva_{t['id']}")
    encerrar = st.checkbox("Encerrar a trilha ao publicar a devolutiva", value=True)
    if st.button("📣 Publicar devolutiva para a turma", type="primary"):
        texto = seguranca.sanitizar(texto, 4000)
        if len(texto) < 50:
            st.error("Escreva uma devolutiva um pouco mais completa.")
            return
        valores = {"devolutiva": texto, "devolutiva_em": db.agora()}
        if encerrar:
            valores["status"] = "encerrada"
        db.atualizar_trilha(t["id"], valores)
        db.auditar(seguranca.autor_atual(), "devolutiva_publicada", f"trilha={t['id']}")
        mensagem, tipo = "Devolutiva publicada. A turma já pode ler na aba Devolutiva da trilha.", "success"
        if canal != opcoes[0]:
            ok, detalhe = teams.avisar(canais[canal], f"📣 Devolutiva da trilha: {t['titulo']}",
                                       [("", "A devolutiva do gestor para a turma está disponível.")],
                                       "Ler a devolutiva", teams.link_trilha(t["id"]))
            mensagem += f" {'✅' if ok else '⚠️'} {detalhe}"
            tipo = "success" if ok else "warning"
        st.session_state["aviso_turma"] = (tipo, mensagem)
        st.rerun()


def _exportar(t: dict, progresso: list[dict], comentarios: list[dict]) -> None:
    propostas = db.listar_propostas(t["id"])
    linhas = [{
        "Data": p["criado_em"], "Participante": p["participante_nome"], "Identificação": p["participante_id"],
        "Versão": p["versao"], "Síntese": p["feedback"].get("sintese", ""), "Leitura do problema": p["leitura"],
        "Proposta": p["proposta"], "Competências mobilizadas": ", ".join(p["feedback"].get("competencias_aplicadas", [])),
        "Encaminhamento": db.STATUS_IDEIA.get(p.get("status_ideia") or "nova", ""),
        "Tempo (min)": round((p["tempo_segundos"] or 0) / 60, 1), "Ritmo atípico": "Sim" if p["ritmo_atipico"] else "Não",
    } for p in propostas]
    if not linhas:
        st.info("Ainda não há propostas para exportar.")
        return
    tabela = pd.DataFrame(linhas).apply(lambda coluna: coluna.map(seguranca.csv_seguro))
    st.download_button(
        "📥 Baixar propostas (CSV para Excel)", data=tabela.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=f"caselab_trilha_{t['id']}_{db.hoje().isoformat()}.csv", mime="text/csv",
        on_click=db.auditar, args=(seguranca.autor_atual(), "exportacao_csv", f"trilha={t['id']}"),
    )
    st.caption(f"{len(progresso)} reflexões de etapas e {len(comentarios)} comentários do mural ficam disponíveis na ferramenta.")


def _privacidade() -> None:
    if not _gestor():
        return
    with st.expander("🛡️ Privacidade (LGPD) — excluir dados de um participante"):
        st.caption("Atende a pedidos de eliminação: remove reflexões, propostas e comentários da pessoa (inclusive os "
                   "comentários recebidos), em todas as trilhas. A ação é auditada de forma pseudonimizada.")
        lista = db.participantes()
        if not lista:
            st.caption("Não há dados de participantes.")
            return
        rotulos = {p["participante_id"]: f"{p['nome']} ({p['participante_id']})" for p in lista}
        pid = st.selectbox("Participante", list(rotulos), format_func=rotulos.get, key="lgpd_participante")
        confirmacao = st.text_input("Digite EXCLUIR para confirmar", key="lgpd_confirmacao")
        if st.button("Excluir dados do participante", disabled=confirmacao.strip() != "EXCLUIR"):
            removidos = db.excluir_dados_participante(pid)
            db.auditar(seguranca.autor_atual(), "lgpd_exclusao", f"participante={seguranca.pseudonimo(pid)} registros={removidos}")
            st.success(f"{removidos} registros excluídos.")
