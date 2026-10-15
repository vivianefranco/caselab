"""Biblioteca de materiais: conteúdos de referência curados pela área de T&D."""
import streamlit as st

from caselab import config, conteudo, db, seguranca


def _pode_editar() -> bool:
    usuario = st.session_state.get("usuario", {})
    return bool(usuario.get("td") or (usuario.get("gestor") and not config.revisao_td_ativa()))


def pagina() -> None:
    seguranca.exigir("gestor", "td")
    st.title("📚 Biblioteca de materiais")
    st.markdown(
        "Materiais de referência que dão base às etapas de conteúdo das trilhas: apostilas, apresentações, "
        "procedimentos e políticas. A curadoria é da área de T&D."
    )
    editar = _pode_editar()

    if editar:
        st.warning("Não inclua dados pessoais nem informações confidenciais: trechos dos materiais são "
                   "processados por um provedor de IA externo.", icon="🔒")
        with st.form("novo_material", clear_on_submit=True):
            nome = st.text_input("Nome do material*", max_chars=200,
                                 placeholder="Ex.: Guia de atendimento ao aluno — versão 2026")
            descricao = st.text_input("Descrição (opcional)", max_chars=300,
                                      placeholder="Origem, área responsável, competências que aborda...")
            arquivo = st.file_uploader(f"Arquivo (PDF, DOCX ou PPTX, até {config.LIMITE_UPLOAD_MB} MB)",
                                       type=conteudo.FORMATOS)
            texto_colado = st.text_area("…ou cole o conteúdo aqui", height=150)
            salvar = st.form_submit_button("Salvar na biblioteca", type="primary")
        if salvar:
            _salvar(nome, descricao, arquivo, texto_colado)
    else:
        st.info("A inclusão de materiais é feita pela área de T&D. Você pode consultar os materiais disponíveis "
                "e escolhê-los ao criar uma trilha.", icon="ℹ️")

    st.divider()
    lista = db.listar_materiais()
    st.markdown(f"### Materiais disponíveis ({len(lista)})")
    if not lista:
        st.info("Nenhum material cadastrado ainda.")
    for m in lista:
        with st.expander(f"📘 {m['nome']}"):
            st.caption(f"{m['tamanho']:,} caracteres · cadastrado em {db.data_br(m['criado_em'])} "
                       f"por {m['criado_por']}".replace(",", "."))
            if m.get("descricao"):
                st.markdown(seguranca.md(m["descricao"]))
            completo = db.obter_material(m["id"])
            st.text_area("Prévia", completo["conteudo"][:1500], height=160, disabled=True, key=f"previa_{m['id']}")
            if editar:
                confirmar = st.checkbox("Quero excluir este material", key=f"conf_exc_{m['id']}")
                if st.button("🗑️ Excluir", key=f"exc_{m['id']}", disabled=not confirmar):
                    db.excluir_material(m["id"])
                    db.auditar(seguranca.autor_atual(), "material_excluido", f"material={m['id']}")
                    st.rerun()


def _salvar(nome, descricao, arquivo, texto_colado) -> None:
    nome = seguranca.sanitizar(nome, 200)
    if not nome:
        st.error("Informe o nome do material.")
        return

    texto = ""
    if arquivo is not None:
        if arquivo.size > config.LIMITE_UPLOAD_MB * 1024 * 1024:
            st.error(f"O arquivo passa de {config.LIMITE_UPLOAD_MB} MB.")
            return
        try:
            with st.spinner("Extraindo o texto do arquivo..."):
                texto = conteudo.extrair_texto(arquivo.name, arquivo.getvalue())
        except ValueError as erro:
            st.error(str(erro))
            return
        except Exception:
            st.error("Não foi possível ler o arquivo. Verifique se ele não está corrompido.")
            return
    if texto_colado:
        texto = f"{texto}\n{texto_colado}" if texto else texto_colado

    texto = seguranca.sanitizar(texto, config.MAX_CHARS_CONTEUDO)
    if len(texto) < 200:
        st.error("Conteúdo muito curto ou sem texto legível. Se for um PDF escaneado (imagem), "
                 "cole o conteúdo como texto.")
        return

    mid = db.criar_material(nome, seguranca.sanitizar(descricao, 300), texto, seguranca.autor_atual())
    db.auditar(seguranca.autor_atual(), "material_criado", f"material={mid}")
    st.success(f"Material “{nome}” salvo com {len(texto):,} caracteres.".replace(",", "."))
