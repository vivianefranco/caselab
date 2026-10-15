"""Autenticação, autorização e proteções de entrada do CaseLab.

Dois modos de acesso:
- Corporativo (recomendado): login único (SSO) via OIDC, ex.: Microsoft Entra ID.
  Ativado quando existe a seção [auth] nos Secrets. Papéis definidos por e-mail
  (GESTORES_EMAILS e TD_EMAILS).
- Demonstração: colaboradores se identificam por nome/matrícula; a área restrita é
  protegida por senha (GESTOR_SENHA para gestores, TD_SENHA para a área de T&D).
"""
import hashlib
import hmac
import re
import time
import unicodedata

import streamlit as st
import streamlit.components.v1 as components

from . import config, db

_TAGS_RESERVADAS = re.compile(
    r"</?\s*(material|problema|leitura|proposta|resposta_provocacao|versao_anterior|propostas|comentarios|reflexoes)\b[^>]*>",
    re.IGNORECASE,
)
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PREFIXO_TRAVADO = "✍️🔒 "


# --- Higienização de entradas ---
def sanitizar(texto, limite: int) -> str:
    """Remove caracteres de controle e as tags que delimitam conteúdo nos prompts
    (evita que alguém 'feche' a tag e injete instruções para a IA)."""
    t = _CONTROLE.sub("", str(texto or ""))
    t = _TAGS_RESERVADAS.sub("", t)
    return t.strip()[:limite]


def normalizar_id(valor) -> str:
    t = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9@._-]", "", t.lower().strip())[:120]


def md(texto) -> str:
    """Escapa '$' para que valores como 'R$ 500' não sejam lidos como fórmula matemática."""
    return str(texto or "").replace("$", r"\$")


def pseudonimo(valor) -> str:
    return hashlib.sha256(str(valor).encode()).hexdigest()[:12]


def csv_seguro(valor):
    """Evita injeção de fórmulas ao abrir o CSV no Excel."""
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


# --- Identidade ---
def _st_user():
    return getattr(st, "user", None) or getattr(st, "experimental_user", None)


def _tela_login_sso():
    st.title("CaseLab")
    st.markdown("Trilhas de aprendizagem que começam por um problema real da equipe.")
    if st.button("Entrar com a conta corporativa", type="primary"):
        st.login()


def usuario_atual() -> dict:
    if config.modo_sso():
        usuario = _st_user()
        if not usuario or not getattr(usuario, "is_logged_in", False):
            _tela_login_sso()
            st.stop()
        email = str(getattr(usuario, "email", "") or "").lower()
        dominios = config.lista("DOMINIOS_PERMITIDOS")
        if dominios and email.split("@")[-1] not in dominios:
            st.error("Sua conta não tem permissão para acessar esta aplicação.")
            if st.button("Sair"):
                st.logout()
            st.stop()
        return {
            "sso": True,
            "id": email,
            "email": email,
            "nome": getattr(usuario, "name", None) or email,
            "gestor": email in config.lista("GESTORES_EMAILS"),
            "td": email in config.lista("TD_EMAILS"),
        }
    return {
        "sso": False, "id": None, "email": None, "nome": None,
        "gestor": bool(st.session_state.get("papel_gestor")),
        "td": bool(st.session_state.get("papel_td")),
    }


def autor_atual() -> str:
    usuario = st.session_state.get("usuario", {})
    if usuario.get("email"):
        return usuario["email"]
    papeis = [p for p, ativo in (("gestor", usuario.get("gestor")), ("T&D", usuario.get("td"))) if ativo]
    return " e ".join(papeis) or "anônimo"


def _confere(senha: str, nome_segredo: str) -> bool:
    configurada = config.segredo(nome_segredo)
    return bool(configurada) and hmac.compare_digest(senha.encode(), str(configurada).encode())


def painel_acesso_restrito() -> None:
    """Login por senha para gestores e área de T&D (somente no modo demonstração)."""
    if config.modo_sso():
        return
    if st.session_state.get("papel_gestor") or st.session_state.get("papel_td"):
        if st.sidebar.button("🔓 Sair da área restrita", width="stretch"):
            st.session_state.papel_gestor = False
            st.session_state.papel_td = False
            st.rerun()
        return

    if not (config.segredo("GESTOR_SENHA") or config.segredo("TD_SENHA")):
        st.sidebar.caption("Área restrita desativada: defina GESTOR_SENHA (e, se quiser, TD_SENHA) nos Secrets.")
        return

    with st.sidebar.expander("🔐 Gestores e área de T&D"):
        if time.time() < st.session_state.get("bloqueado_ate", 0):
            st.warning("Muitas tentativas incorretas. Aguarde alguns minutos.")
            return
        with st.form("login_restrito", clear_on_submit=True):
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar")
        if entrar:
            gestor, td = _confere(senha, "GESTOR_SENHA"), _confere(senha, "TD_SENHA")
            if gestor or td:
                st.session_state.papel_gestor = gestor
                st.session_state.papel_td = td
                st.session_state.falhas_login = 0
                db.auditar("gestor" if gestor else "T&D", "login_area_restrita")
                st.rerun()
            else:
                falhas = st.session_state.get("falhas_login", 0) + 1
                st.session_state.falhas_login = falhas
                db.auditar("desconhecido", "login_falhou", f"tentativa={falhas}")
                if falhas >= 5:
                    st.session_state.bloqueado_ate = time.time() + 300
                st.error("Senha incorreta.")


def exigir(*papeis: str) -> None:
    """Defesa em profundidade: cada tela restrita confere a permissão de novo."""
    usuario = st.session_state.get("usuario", {})
    if not any(usuario.get(p) for p in papeis):
        st.error("Acesso restrito.")
        st.stop()


# --- Autoria da resposta ---
_JS_BLOQUEIO = """
<script>
(function () {
  const doc = window.parent.document;
  const SELETOR = 'textarea[aria-label^="%PREFIXO%"]';
  function avisar() {
    let aviso = doc.getElementById('caselab-aviso-colar');
    if (!aviso) {
      aviso = doc.createElement('div');
      aviso.id = 'caselab-aviso-colar';
      aviso.setAttribute('role', 'alert');
      aviso.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);' +
        'z-index:99999;background:#b42318;color:#fff;padding:10px 18px;border-radius:8px;' +
        'font:14px sans-serif;box-shadow:0 4px 12px rgba(0,0,0,.25);max-width:90vw;text-align:center';
      aviso.textContent = 'Para garantir a autoria, este campo não aceita colar texto. Escreva com suas palavras.';
      doc.body.appendChild(aviso);
    }
    aviso.style.display = 'block';
    clearTimeout(aviso._timer);
    aviso._timer = setTimeout(function () { aviso.style.display = 'none'; }, 3500);
  }
  function proteger() {
    doc.querySelectorAll(SELETOR).forEach(function (campo) {
      if (campo.dataset.caselabSemColar) return;
      campo.dataset.caselabSemColar = '1';
      ['paste', 'drop'].forEach(function (evento) {
        campo.addEventListener(evento, function (e) { e.preventDefault(); avisar(); });
      });
    });
  }
  proteger();
  new MutationObserver(proteger).observe(doc.body, { childList: true, subtree: true });
})();
</script>
"""


def bloquear_colar() -> None:
    """Impede colar/arrastar texto nos campos de resposta cujo rótulo começa com PREFIXO_TRAVADO.
    É uma barreira de dissuasão (não uma garantia absoluta) e funciona junto com o registro
    do tempo de elaboração, a declaração de autoria e o mural, que só abre após a primeira versão."""
    components.html(_JS_BLOQUEIO.replace("%PREFIXO%", PREFIXO_TRAVADO.strip()), height=0)
