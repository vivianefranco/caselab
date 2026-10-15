"""Configurações centrais do CaseLab.

Tudo que é sensível (chaves, senhas, URLs de webhook, banco) vem dos Secrets do
Streamlit Cloud ou, ao rodar localmente, do arquivo .env. Nada disso fica no código.
"""
import os
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(RAIZ, ".env"))


def segredo(nome: str, padrao=None):
    """Lê primeiro dos Secrets do Streamlit; se não houver, do .env / variáveis de ambiente."""
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass  # Sem secrets.toml (ex.: rodando localmente só com .env)
    valor = os.getenv(nome)
    return valor if valor not in (None, "") else padrao


def _primeiro(*nomes, padrao=None):
    for nome in nomes:
        valor = segredo(nome)
        if valor not in (None, ""):
            return valor
    return padrao


def _inteiro(nome: str, padrao: int) -> int:
    try:
        return int(segredo(nome, padrao))
    except (TypeError, ValueError):
        return padrao


# --- Provedor de IA (qualquer API compatível com OpenAI: Qwen, Azure OpenAI, etc.) ---
LLM_API_KEY = _primeiro("LLM_API_KEY", "QWEN_API_KEY")
LLM_BASE_URL = _primeiro(
    "LLM_BASE_URL", "QWEN_BASE_URL",
    padrao="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
LLM_MODELO = _primeiro("LLM_MODEL", "QWEN_MODEL", padrao="qwen-plus")

# --- Aplicação ---
APP_URL = str(segredo("APP_URL", "http://localhost:8501")).rstrip("/")
DATABASE_URL = segredo("DATABASE_URL")
FUSO = ZoneInfo(str(segredo("FUSO_HORARIO", "America/Sao_Paulo")))
CONTATO_PRIVACIDADE = str(segredo(
    "CONTATO_PRIVACIDADE",
    "o RH ou o Encarregado de Proteção de Dados (DPO) da sua organização",
))

# --- Limites (controle de custo, abuso e tamanho de dados) ---
MAX_MENTORIAS_DIA = _inteiro("MAX_MENTORIAS_DIA", _inteiro("MAX_AVALIACOES_DIA", 10))  # por participante
MAX_GERACOES_SESSAO = _inteiro("MAX_GERACOES_SESSAO", 15)  # chamadas de criação por sessão do gestor
RITMO_ATIPICO_CPM = _inteiro("RITMO_ATIPICO_CPM", 400)     # caracteres por minuto
LIMITE_UPLOAD_MB = 10
MAX_CHARS_CONTEUDO = 300_000
MIN_CHARS_PROPOSTA = 150
MIN_CHARS_REFLEXAO = 60


def modo_sso() -> bool:
    """True quando o login corporativo (OIDC, ex.: Microsoft Entra ID) está configurado."""
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def revisao_td_ativa() -> bool:
    """A revisão pela área de T&D é obrigatória quando esse papel está configurado."""
    if modo_sso():
        return bool(lista("TD_EMAILS"))
    return bool(segredo("TD_SENHA"))


def lista(nome: str) -> list[str]:
    """Lê uma lista dos Secrets (lista TOML ou texto separado por vírgulas), em minúsculas."""
    valor = segredo(nome, [])
    if isinstance(valor, str):
        valor = valor.replace(";", ",").split(",")
    return [str(v).strip().lower() for v in valor if str(v).strip()]


def canais_teams() -> dict[str, str]:
    """Canais do Teams configurados pela TI nos Secrets, no formato {nome: url}."""
    canais: dict[str, str] = {}
    try:
        if "teams_canais" in st.secrets:
            canais.update({str(k): str(v) for k, v in st.secrets["teams_canais"].items()})
    except Exception:
        pass
    unico = segredo("TEAMS_WEBHOOK_URL")
    if unico and not canais:
        canais["Canal padrão"] = str(unico)
    return canais
