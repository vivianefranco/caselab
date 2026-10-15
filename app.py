"""CaseLab — trilhas de aprendizagem que começam por um problema real da equipe.

Ponto de entrada da aplicação Streamlit. A lógica fica no pacote `caselab/`.
"""
import os

import streamlit as st

from caselab import config

RAIZ = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(RAIZ, "logo.png")
ICONE = os.path.join(RAIZ, "logo_icone.png")

st.set_page_config(
    page_title="CaseLab | Aprender resolvendo problemas reais",
    page_icon=ICONE if os.path.exists(ICONE) else "🧭",
    layout="centered",
)

from caselab import db, seguranca  # noqa: E402
from caselab.telas import biblioteca, colaborador, inicio, trilhas, turma  # noqa: E402

if not config.LLM_API_KEY:
    st.error("⚠️ A chave da IA (`LLM_API_KEY`) não foi configurada nos Secrets do Streamlit nem no arquivo `.env`.")
    st.stop()

db.init()
usuario = seguranca.usuario_atual()
st.session_state["usuario"] = usuario

if os.path.exists(LOGO):
    st.sidebar.image(LOGO, width=220)

seguranca.painel_acesso_restrito()

pagina_inicio = st.Page(inicio.pagina, title="Início", icon="🏠", url_path="inicio", default=True)
pagina_trilhas = st.Page(colaborador.pagina, title="Minhas trilhas", icon="🧭", url_path="trilhas")
st.session_state["pagina_trilhas"] = pagina_trilhas

paginas = {"": [pagina_inicio, pagina_trilhas]}
restritas = []
if usuario["gestor"] or usuario["td"]:
    restritas += [
        st.Page(trilhas.pagina, title="Criar e revisar trilhas", icon="🛠️", url_path="gestao"),
        st.Page(turma.pagina, title="Acompanhar a turma", icon="👥", url_path="turma"),
        st.Page(biblioteca.pagina, title="Biblioteca de materiais", icon="📚", url_path="biblioteca"),
    ]
if restritas:
    paginas["Gestores e T&D"] = restritas
navegacao = st.navigation(paginas)

with st.sidebar:
    if usuario["sso"]:
        papeis = [p for p, ativo in (("gestor", usuario["gestor"]), ("T&D", usuario["td"])) if ativo]
        st.caption(f"Conectado como **{usuario['nome']}**" + (f" · {' e '.join(papeis)}" if papeis else ""))
        if st.button("Sair", width="stretch"):
            st.logout()
    with st.expander("🛡️ Privacidade e uso de dados"):
        st.markdown(f"""
- **O que é coletado:** nome, matrícula ou e-mail corporativo, reflexões das etapas, propostas, comentários no mural, a mentoria da IA e o tempo de elaboração.
- **Para quê:** desenvolvimento profissional e melhoria da equipe. Não há nota e nada é usado em avaliação de desempenho.
- **Quem vê:** suas reflexões e a mentoria, só você e os gestores da trilha. Suas propostas e comentários, também os colegas da turma, no mural.
- **IA:** apenas os textos são enviados ao provedor de IA — seu nome não.
- **Seus direitos:** para acessar, corrigir ou excluir seus dados, procure {config.CONTATO_PRIVACIDADE}.
""")

navegacao.run()
