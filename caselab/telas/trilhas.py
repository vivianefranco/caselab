"""Gestor e área de T&D: criar a trilha (problema → quem → competências → materiais),
revisar, aprovar e publicar."""
import re
from datetime import date, timedelta
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from caselab import config, conteudo, db, ia, seguranca, teams
from caselab.telas import colaborador

VISOES = ["✨ Nova trilha", "📝 Editar e revisar", "🗂️ Todas as trilhas"]
_RECURSO = re.compile(r"^(.*?)\s*\|\s*(https://\S+)$")


def _papel(nome: str) -> bool:
    return bool(st.session_state.get("usuario", {}).get(nome))


def _avisar(tipo: str, texto: str) -> None:
    st.session_state["aviso_trilhas"] = (tipo, texto)


def _abrir(tid: int) -> None:
    st.session_state["trilha_em_edicao"] = tid
    st.session_state["ir_para_trilhas"] = VISOES[1]


def _limite_geracoes() -> bool:
    if st.session_state.get("geracoes", 0) >= config.MAX_GERACOES_SESSAO:
        st.error("Limite de uso da IA nesta sessão atingido. Recarregue a página mais tarde.")
        return True
    st.session_state["geracoes"] = st.session_state.get("geracoes", 0) + 1
    return False


def pagina() -> None:
    seguranca.exigir("gestor", "td")
    st.title("🧭 Trilhas")
    if "ir_para_trilhas" in st.session_state:
        st.session_state["visao_trilhas"] = st.session_state.pop("ir_para_trilhas")
    visao = st.radio("Etapa", VISOES, horizontal=True, key="visao_trilhas", label_visibility="collapsed")
    aviso = st.session_state.pop("aviso_trilhas", None)
    if aviso:
        getattr(st, aviso[0])(aviso[1])

    if visao == VISOES[0]:
        _nova()
    elif visao == VISOES[1]:
        _editar()
    else:
        _todas()


# --- 1. Nova trilha: problema → quem → competências → materiais ---
def _sugerir_competencias() -> None:
    problema = seguranca.sanitizar(st.session_state.get("nt_problema"), 2000)
    publico = seguranca.sanitizar(st.session_state.get("nt_publico"), 300)
    if len(problema) < 30 or not publico:
        st.session_state["nt_erro"] = "Descreva o problema e o público antes de pedir sugestões."
        return
    if st.session_state.get("geracoes", 0) >= config.MAX_GERACOES_SESSAO:
        st.session_state["nt_erro"] = "Limite de uso da IA nesta sessão atingido."
        return
    st.session_state["geracoes"] = st.session_state.get("geracoes", 0) + 1
    try:
        sugestoes = ia.sugerir_competencias(problema, publico, seguranca.sanitizar(st.session_state.get("nt_contexto"), 1500))
    except ia.ErroIA as erro:
        st.session_state["nt_erro"] = str(erro)
        return
    st.session_state["nt_competencias"] = "\n".join(sugestoes)


def _nova() -> None:
    st.markdown("Comece pelo **problema** que a equipe precisa resolver. Depois diga **quem** vai participar, "
                "**quais competências** são necessárias e **com quais materiais** a trilha será construída.")
    erro = st.session_state.pop("nt_erro", None)
    if erro:
        st.error(erro)

    with st.container(border=True):
        st.markdown("**1. O problema**")
        st.text_area("Que problema a equipe precisa resolver? Como ele aparece no dia a dia e que impacto tem?*",
                     key="nt_problema", max_chars=2000, height=130,
                     placeholder="Ex.: os alunos esperam muito pela primeira resposta nos canais de atendimento; "
                                 "reclamações cresceram 30% no semestre e parte das dúvidas se repete.")
    with st.container(border=True):
        st.markdown("**2. Quem**")
        st.text_input("Cargo ou função dos participantes*", key="nt_publico", max_chars=300,
                      placeholder="Ex.: Analistas de atendimento ao aluno (nível pleno)")
        st.text_area("Contexto da equipe", key="nt_contexto", max_chars=1500, height=90,
                     placeholder="Atividades, sistemas, públicos atendidos, tamanho da equipe.")
        st.caption("A complexidade do caso é ajustada ao cargo e à função informados.")
    with st.container(border=True):
        st.markdown("**3. Competências necessárias** — uma por linha")
        st.text_area("Competências", key="nt_competencias", max_chars=1500, height=120, label_visibility="collapsed",
                     placeholder="Ex.:\nPriorização: decidir o que atender primeiro\nComunicação escrita: respostas claras e empáticas")
        st.button("💡 Sugerir competências com IA", on_click=_sugerir_competencias,
                  help="Usa o problema e o público para sugerir competências. Você pode editar a lista.")
    with st.container(border=True):
        st.markdown("**4. Materiais de referência**")
        materiais = db.listar_materiais()
        nomes = {m["id"]: m["nome"] for m in materiais}
        escolhidos = st.multiselect("Materiais da biblioteca", list(nomes), format_func=nomes.get, key="nt_materiais",
                                    placeholder="Escolha os materiais que dão base aos conteúdos")
        if not materiais:
            st.caption("A biblioteca ainda está vazia. Peça à área de T&D para cadastrar os materiais.")
        elif not escolhidos:
            st.caption("Sem materiais, a IA usa conhecimento geral e a revisão da área de T&D se torna essencial.")

    if not st.button("✨ Gerar rascunho da trilha", type="primary"):
        return

    problema = seguranca.sanitizar(st.session_state.get("nt_problema"), 2000)
    publico = seguranca.sanitizar(st.session_state.get("nt_publico"), 300)
    competencias = ia.lista_limpa(seguranca.sanitizar(st.session_state.get("nt_competencias"), 1500), 8, 200)
    if len(problema) < 30 or not publico:
        st.error("Descreva o problema (pelo menos uma frase completa) e o cargo ou função dos participantes.")
        return
    if len(competencias) < 2:
        st.error("Informe pelo menos duas competências — ou peça sugestões à IA.")
        return
    if _limite_geracoes():
        return

    textos = [db.obter_material(mid)["conteudo"] for mid in escolhidos]
    trechos = conteudo.selecionar_trechos("\n\n".join(textos), f"{problema} {' '.join(competencias)}", k=6) if textos else []
    base = {"problema": problema, "publico": publico, "contexto_equipe": seguranca.sanitizar(st.session_state.get("nt_contexto"), 1500),
            "competencias": competencias, "materiais_ids": list(escolhidos)}

    with st.spinner("A IA está rascunhando o caso, a entrega e as etapas de conteúdo..."):
        try:
            rascunho = ia.gerar_trilha(base, trechos)
        except ia.ErroIA as erro:
            st.error(str(erro))
            return

    tid = db.criar_trilha({**base, **rascunho, "trechos": trechos, "gerado_sem_material": not trechos,
                           "criado_por": seguranca.autor_atual()})
    db.auditar(seguranca.autor_atual(), "trilha_criada", f"trilha={tid}")
    for chave in ("nt_problema", "nt_publico", "nt_contexto", "nt_competencias", "nt_materiais"):
        st.session_state.pop(chave, None)
    _avisar("success", "Rascunho criado! Revise o caso e as etapas e ajuste o que quiser.")
    _abrir(tid)
    st.rerun()


# --- 2. Editar, revisar, aprovar e publicar ---
def _pode_editar(t: dict) -> bool:
    if t["status"] == "rascunho":
        return _papel("gestor") or _papel("td")
    if t["status"] == "em_revisao":
        return _papel("td")
    return False


def _editar() -> None:
    lista = db.listar_trilhas()
    if not lista:
        st.info("Nenhuma trilha criada ainda. Comece em **✨ Nova trilha**.")
        return
    rotulos = {t["id"]: f"{db.STATUS_TRILHA.get(t['status'], t['status'])} · #{t['id']} · {t['titulo']}" for t in lista}
    ids = list(rotulos)
    atual = st.session_state.get("trilha_em_edicao", ids[0])
    tid = st.selectbox("Trilha", ids, index=ids.index(atual) if atual in ids else 0, format_func=rotulos.get)
    st.session_state["trilha_em_edicao"] = tid
    t = db.obter_trilha(tid)
    editavel = _pode_editar(t)

    _mensagem_status(t)
    _resumo_pedido(t)
    _formulario(t, editavel)

    with st.expander("👀 Pré-visualizar como a turma verá"):
        colaborador.mostrar_caso(t)
        for i, etapa in enumerate(t["etapas"]):
            with st.container(border=True):
                colaborador.mostrar_etapa(etapa, i)
    if t["trechos"]:
        with st.expander("📎 Trechos dos materiais usados como base"):
            for i, trecho in enumerate(t["trechos"], 1):
                st.markdown(f"**Trecho {i}**")
                st.text(trecho[:1500])

    st.divider()
    _acoes(t)


def _mensagem_status(t: dict) -> None:
    status = t["status"]
    if t.get("gerado_sem_material"):
        st.warning("Esta trilha foi gerada sem materiais da biblioteca. Os conteúdos precisam de revisão cuidadosa.", icon="⚠️")
    if t.get("nota_revisao") and status in ("rascunho", "em_revisao", "aprovada"):
        st.info(f"**Observações da área de T&D:** {seguranca.md(t['nota_revisao'])}", icon="🗒️")
    textos = {
        "rascunho": "Rascunho: revise e ajuste. " + ("Quando estiver pronto, envie para a revisão da área de T&D."
                                                       if config.revisao_td_ativa() else "Quando estiver pronto, publique."),
        "em_revisao": "Em revisão pela área de T&D. " + ("Você pode editar, aprovar ou devolver ao gestor."
                                                          if _papel("td") else "Aguarde a aprovação para publicar."),
        "aprovada": f"Aprovada por {t.get('aprovado_por')} em {db.data_br(t.get('aprovado_em'))}. Pronta para publicar.",
        "publicada": "Publicada: o conteúdo fica travado para que toda a turma percorra a mesma trilha.",
        "encerrada": "Encerrada: a trilha não recebe mais participações.",
    }
    st.caption(textos.get(status, ""))


def _resumo_pedido(t: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**Problema:** {seguranca.md(t['problema'])}")
        st.markdown(f"**Quem:** {seguranca.md(t['publico'])}")
        if t.get("contexto_equipe"):
            st.caption(seguranca.md(t["contexto_equipe"]))
        st.markdown("**Competências:** " + " · ".join(seguranca.md(c.split(':', 1)[0]) for c in t["competencias"]))


def _limpar_campos_etapas(tid: int) -> None:
    """Descarta o estado dos campos das etapas para que reflitam o que foi salvo."""
    for chave in [k for k in st.session_state if str(k).startswith("e_") and f"_{tid}_" in str(k)]:
        del st.session_state[chave]


def _formatar_recursos(recursos: list[dict]) -> str:
    return "\n".join(f"{r['titulo']} | {r['url']}" for r in recursos)


def _ler_recursos(texto: str) -> tuple[list[dict], list[str]]:
    recursos, invalidas = [], []
    for linha in seguranca.sanitizar(texto, 3000).splitlines():
        linha = linha.strip()
        if not linha:
            continue
        achado = _RECURSO.match(linha)
        if achado and urlparse(achado.group(2)).hostname:
            recursos.append({"titulo": achado.group(1).strip()[:200] or achado.group(2), "url": achado.group(2)[:500]})
        else:
            invalidas.append(linha)
    return recursos[:8], invalidas


def _formulario(t: dict, editavel: bool) -> None:
    bloqueado = not editavel
    with st.form(f"editar_{t['id']}"):
        st.markdown("#### O caso")
        titulo = st.text_input("Título", value=t["titulo"] or "", max_chars=300, disabled=bloqueado)
        caso = st.text_area("📋 Caso", value=t["caso"] or "", height=240, disabled=bloqueado)
        pergunta = st.text_area("🚀 Convite à turma", value=t["pergunta"] or "", height=90, disabled=bloqueado)
        entrega = st.text_area("📦 Entrega esperada (definida a partir do caso)", value=t["entrega"] or "",
                               height=90, disabled=bloqueado)

        st.markdown("#### Etapas de desenvolvimento")
        st.caption("Liberadas em sequência: a próxima abre quando o participante conclui a reflexão da anterior. "
                   "Recursos complementares: um por linha, no formato `Título | https://endereço`.")
        etapas_editadas = []
        for i, e in enumerate(t["etapas"]):
            with st.expander(f"Etapa {i + 1}: {e['titulo']}", expanded=False):
                c1, c2 = st.columns(2)
                etapa = {
                    "titulo": c1.text_input("Título da etapa", value=e["titulo"], key=f"e_tit_{t['id']}_{i}", disabled=bloqueado),
                    "competencia": c2.text_input("Competência", value=e["competencia"], key=f"e_comp_{t['id']}_{i}", disabled=bloqueado),
                    "conteudo": st.text_area("Conteúdo (Markdown)", value=e["conteudo"], height=260, key=f"e_cont_{t['id']}_{i}", disabled=bloqueado),
                    "exemplo": st.text_area("Exemplo de aplicação", value=e["exemplo"], height=100, key=f"e_ex_{t['id']}_{i}", disabled=bloqueado),
                    "reflexao": st.text_area("Reflexão aplicada ao caso", value=e["reflexao"], height=80, key=f"e_ref_{t['id']}_{i}", disabled=bloqueado),
                    "recursos_texto": st.text_area("Recursos complementares da T&D", value=_formatar_recursos(e.get("recursos") or []),
                                                   height=80, key=f"e_rec_{t['id']}_{i}", disabled=bloqueado,
                                                   placeholder="Curso de comunicação | https://..."),
                    "remover": st.checkbox("Remover esta etapa", key=f"e_rem_{t['id']}_{i}", disabled=bloqueado),
                }
                etapas_editadas.append(etapa)
        nova_etapa = st.checkbox("Adicionar uma etapa em branco ao salvar", disabled=bloqueado)

        st.markdown("#### Regras")
        c1, c2, c3 = st.columns(3)
        limite = c1.number_input("Limite de caracteres da proposta", 500, 6000, int(t["limite_chars"] or 3000), 100, disabled=bloqueado)
        versoes = c2.number_input("Versões da proposta por pessoa", 1, 3, int(t["max_versoes"] or 2), disabled=bloqueado,
                                  help="Com 2 ou mais, o participante lapida a ideia depois da mentoria e dos comentários.")
        bloquear = c3.toggle("Bloquear colar texto", value=bool(t["bloquear_colar"]), disabled=bloqueado,
                             help="Desative se algum participante precisar de recursos de acessibilidade que dependem de colar.")
        c4, c5 = st.columns(2)
        usar_prazo = c4.checkbox("Definir prazo", value=bool(t["prazo"]), disabled=bloqueado)
        prazo = c5.date_input("Prazo", value=date.fromisoformat(t["prazo"]) if t["prazo"] else date.today() + timedelta(days=21),
                              format="DD/MM/YYYY", disabled=bloqueado)

        nota = t.get("nota_revisao") or ""
        if _papel("td") and t["status"] in ("rascunho", "em_revisao"):
            nota = st.text_area("🗒️ Observações da área de T&D (visíveis para o gestor)", value=nota, height=80, disabled=bloqueado)
        salvar = st.form_submit_button("💾 Salvar alterações", disabled=bloqueado)

    if not salvar:
        return

    etapas, problemas = [], []
    for i, e in enumerate(etapas_editadas, 1):
        if e["remover"]:
            continue
        recursos, invalidas = _ler_recursos(e["recursos_texto"])
        problemas += [f"Etapa {i}: “{linha[:60]}”" for linha in invalidas]
        etapas.append(ia.normalizar_etapa({
            "titulo": seguranca.sanitizar(e["titulo"], 200), "competencia": seguranca.sanitizar(e["competencia"], 200),
            "conteudo": seguranca.sanitizar(e["conteudo"], 6000), "exemplo": seguranca.sanitizar(e["exemplo"], 2000),
            "reflexao": seguranca.sanitizar(e["reflexao"], 600), "recursos": recursos,
        }))
    if nova_etapa:
        etapas.append(ia.normalizar_etapa({"titulo": "Nova etapa", "conteudo": "Escreva aqui o conteúdo da etapa.",
                                           "reflexao": "Como este conteúdo ajuda a resolver o caso?"}))
    if problemas:
        st.error("Recursos com formato inválido (use `Título | https://endereço`): " + "; ".join(problemas))
        return
    titulo, caso, pergunta = seguranca.sanitizar(titulo, 300), seguranca.sanitizar(caso, 6000), seguranca.sanitizar(pergunta, 1500)
    if not (titulo and caso and pergunta and seguranca.sanitizar(entrega, 1500)):
        st.error("Título, caso, convite e entrega esperada são obrigatórios.")
        return
    if not etapas or any(not (e["titulo"] and e["conteudo"] and e["reflexao"]) for e in etapas):
        st.error("Cada etapa precisa de título, conteúdo e reflexão — e a trilha precisa de pelo menos uma etapa.")
        return

    db.atualizar_trilha(t["id"], {
        "titulo": titulo, "caso": caso, "pergunta": pergunta, "entrega": seguranca.sanitizar(entrega, 1500),
        "etapas": etapas, "limite_chars": int(limite), "max_versoes": int(versoes), "bloquear_colar": bool(bloquear),
        "prazo": prazo.isoformat() if usar_prazo else None, "nota_revisao": seguranca.sanitizar(nota, 2000) or None,
    })
    db.auditar(seguranca.autor_atual(), "trilha_editada", f"trilha={t['id']}")
    _limpar_campos_etapas(t["id"])
    _avisar("success", "Alterações salvas.")
    st.rerun()


def _acoes(t: dict) -> None:
    status = t["status"]
    revisao = config.revisao_td_ativa()

    if status == "rascunho" and (_papel("gestor") or _papel("td")):
        st.markdown("### Próximo passo")
        if revisao:
            if st.button("📨 Enviar para revisão da área de T&D", type="primary"):
                db.atualizar_trilha(t["id"], {"status": "em_revisao", "enviado_revisao_em": db.agora()})
                db.auditar(seguranca.autor_atual(), "trilha_enviada_revisao", f"trilha={t['id']}")
                _avisar("success", "Trilha enviada para revisão. A área de T&D verá na lista de trilhas em revisão.")
                st.rerun()
        else:
            _publicar(t)
        c1, c2 = st.columns(2)
        with c1:
            ok = st.checkbox("Substituir o rascunho atual", key=f"conf_regerar_{t['id']}")
            if st.button("🔄 Gerar nova versão com IA", disabled=not ok):
                _regerar(t)
        with c2:
            ok = st.checkbox("Quero excluir este rascunho", key=f"conf_excluir_{t['id']}")
            if st.button("🗑️ Excluir rascunho", disabled=not ok):
                db.excluir_trilha(t["id"])
                db.auditar(seguranca.autor_atual(), "trilha_excluida", f"trilha={t['id']}")
                st.session_state.pop("trilha_em_edicao", None)
                _avisar("info", "Rascunho excluído.")
                st.rerun()

    elif status == "em_revisao" and _papel("td"):
        st.markdown("### Revisão da área de T&D")
        c1, c2 = st.columns(2)
        if c1.button("✅ Aprovar trilha", type="primary"):
            db.atualizar_trilha(t["id"], {"status": "aprovada", "aprovado_por": seguranca.autor_atual(), "aprovado_em": db.agora()})
            db.auditar(seguranca.autor_atual(), "trilha_aprovada", f"trilha={t['id']}")
            _avisar("success", "Trilha aprovada. O gestor já pode publicar para a turma.")
            st.rerun()
        if c2.button("↩️ Devolver ao gestor"):
            db.atualizar_trilha(t["id"], {"status": "rascunho"})
            db.auditar(seguranca.autor_atual(), "trilha_devolvida", f"trilha={t['id']}")
            _avisar("info", "Trilha devolvida ao gestor com as observações registradas.")
            st.rerun()

    elif status == "aprovada" and _papel("gestor"):
        st.markdown("### Publicar para a turma")
        _publicar(t)

    elif status == "publicada":
        st.markdown("**🔗 Link para a turma**")
        st.code(teams.link_trilha(t["id"]), language=None)
        if _papel("gestor") and st.button("⏹️ Encerrar trilha"):
            db.atualizar_trilha(t["id"], {"status": "encerrada"})
            db.auditar(seguranca.autor_atual(), "trilha_encerrada", f"trilha={t['id']}")
            _avisar("info", "Trilha encerrada.")
            st.rerun()

    if status != "rascunho" and st.button("📄 Duplicar como novo rascunho"):
        campos = ("problema", "publico", "contexto_equipe", "competencias", "materiais_ids", "caso", "pergunta", "entrega",
                  "etapas", "trechos", "gerado_sem_material", "limite_chars", "max_versoes", "bloquear_colar")
        novo = db.criar_trilha({**{c: t[c] for c in campos}, "titulo": f"{t['titulo']} (cópia)", "criado_por": seguranca.autor_atual()})
        db.auditar(seguranca.autor_atual(), "trilha_duplicada", f"origem={t['id']} nova={novo}")
        _avisar("success", "Cópia criada como rascunho.")
        _abrir(novo)
        st.rerun()


def _publicar(t: dict) -> None:
    canais = config.canais_teams()
    opcoes = ["Não avisar no Teams (só gerar o link)"] + list(canais)
    canal = st.selectbox("Avisar a turma no canal do Teams", opcoes, help="Os canais são configurados pela TI nos Secrets.")
    if not st.button("🚀 Publicar trilha", type="primary"):
        return
    db.atualizar_trilha(t["id"], {"status": "publicada", "publicado_em": db.agora()})
    db.auditar(seguranca.autor_atual(), "trilha_publicada", f"trilha={t['id']} canal={canal}")
    link = teams.link_trilha(t["id"])
    tipo, mensagem = "success", f"🎉 Trilha publicada! Link para a turma: {link}"
    if canal != opcoes[0]:
        ok, detalhe = teams.avisar(
            canais[canal], f"🧭 Nova trilha: {t['titulo']}",
            [("Por que esta trilha", t["pergunta"]),
             ("Como funciona", f"{len(t['etapas'])} etapas curtas de conteúdo e, ao final, cada pessoa propõe uma solução "
                               "e contribui com as ideias dos colegas. Não há nota nem resposta certa.")]
            + ([("Prazo", db.data_br(t["prazo"]))] if t.get("prazo") else []),
            "Começar a trilha", link)
        mensagem += f"\n\n{'✅' if ok else '⚠️'} {detalhe}"
        tipo = "success" if ok else "warning"
    _avisar(tipo, mensagem)
    st.rerun()


def _regerar(t: dict) -> None:
    if _limite_geracoes():
        return
    with st.spinner("Gerando uma nova versão..."):
        try:
            rascunho = ia.gerar_trilha(t, t["trechos"])
        except ia.ErroIA as erro:
            st.error(str(erro))
            return
    db.atualizar_trilha(t["id"], rascunho)
    db.auditar(seguranca.autor_atual(), "trilha_regerada", f"trilha={t['id']}")
    _limpar_campos_etapas(t["id"])
    _avisar("success", "Nova versão gerada. Revise antes de seguir.")
    st.rerun()


# --- 3. Visão geral ---
def _todas() -> None:
    lista = db.listar_trilhas()
    if not lista:
        st.info("Nenhuma trilha criada ainda.")
        return
    if _papel("td"):
        pendentes = [t for t in lista if t["status"] == "em_revisao"]
        if pendentes:
            st.warning(f"{len(pendentes)} trilha(s) aguardando revisão da área de T&D.", icon="🔎")
    tabela = pd.DataFrame([{
        "ID": t["id"], "Título": t["titulo"], "Status": db.STATUS_TRILHA.get(t["status"], t["status"]),
        "Público": t["publico"], "Criada por": t["criado_por"], "Criada em": db.data_br(t["criado_em"]),
        "Publicada em": db.data_br(t["publicado_em"]), "Prazo": db.data_br(t["prazo"]),
    } for t in lista])
    st.dataframe(tabela, hide_index=True, width="stretch")
    rotulos = {t["id"]: f"#{t['id']} · {t['titulo']}" for t in lista}
    c1, c2 = st.columns([3, 1])
    escolhida = c1.selectbox("Abrir trilha", list(rotulos), format_func=rotulos.get, label_visibility="collapsed")
    if c2.button("Abrir", width="stretch"):
        _abrir(escolhida)
        st.rerun()
