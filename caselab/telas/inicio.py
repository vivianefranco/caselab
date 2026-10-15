"""Página inicial: deixa explícito o objetivo, o percurso e o papel de cada um."""
import streamlit as st

from caselab import config


def pagina() -> None:
    st.title("CaseLab")
    st.markdown("### Aprender resolvendo um problema real da equipe")
    st.markdown(
        "O CaseLab apoia uma equipe a **desenvolver as competências de que precisa para resolver um problema "
        "real da própria área**. Cada trilha começa pelo caso: os conteúdos chegam ao longo do percurso, no "
        "momento em que a turma precisa deles, e a trilha termina em propostas que a turma constrói e compartilha."
    )
    st.info("Não há nota nem resposta certa. O que se acompanha é o desenvolvimento das competências e a "
            "qualidade das soluções que a equipe produz.", icon="🌱")

    st.markdown("#### Como funciona")
    passos = [
        ("1", "O gestor traz o problema", "Registra o problema, quem precisa se desenvolver e as competências necessárias."),
        ("2", "A trilha é montada e revisada", "A IA rascunha o caso, a entrega e as etapas a partir dos materiais; "
                                              "a área de T&D revisa e aprova."),
        ("3", "A turma aprende em etapas", "Cada etapa traz um conteúdo curto, um exemplo e uma reflexão aplicada ao caso."),
        ("4", "Cada pessoa propõe uma solução", "Com mentoria da IA, sem nota, e com a possibilidade de lapidar a ideia."),
        ("5", "A turma troca no mural", "Todos leem e comentam as propostas dos colegas."),
        ("6", "O gestor fecha com a turma", "Recebe uma síntese, faz uma devolutiva coletiva e escolhe ideias para testar."),
    ]
    colunas = st.columns(3)
    for indice, (numero, titulo, texto) in enumerate(passos):
        with colunas[indice % 3], st.container(border=True):
            st.markdown(f"**{numero}. {titulo}**")
            st.caption(texto)

    st.markdown("#### Quem faz o quê")
    st.markdown(
        "- **Área de T&D:** mantém a biblioteca de materiais e aprova as trilhas antes da publicação.\n"
        "- **Gestor:** traz o problema, acompanha a turma e faz a devolutiva coletiva — sem precisar conduzir "
        "o treinamento nem responder pessoa por pessoa.\n"
        "- **Colaborador:** percorre a trilha, propõe soluções e contribui com as ideias dos colegas.\n"
        "- **IA:** rascunha, faz a mentoria e sintetiza. Não decide: toda trilha passa por revisão humana."
    )

    usuario = st.session_state.get("usuario", {})
    st.divider()
    if usuario.get("gestor") or usuario.get("td"):
        st.markdown("Use o menu lateral para criar, revisar e acompanhar trilhas.")
    pagina_trilhas = st.session_state.get("pagina_trilhas")
    if pagina_trilhas is not None:
        st.page_link(pagina_trilhas, label="Ir para minhas trilhas", icon="🧭")
    if not config.modo_sso():
        st.caption("Gestores e área de T&D: entrem pela área restrita, no menu lateral.")
