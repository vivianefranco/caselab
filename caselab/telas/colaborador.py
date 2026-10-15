"""Tela do colaborador: percorrer a trilha (caso → etapas → proposta → mural → devolutiva)."""
import time

import streamlit as st

from caselab import config, db, ia, seguranca
from caselab.seguranca import md


# --- Componentes reutilizados na pré-visualização e no acompanhamento do gestor ---
def mostrar_caso(t: dict) -> None:
    st.subheader(f"🧭 {t['titulo']}")
    if t.get("prazo"):
        st.caption(f"Prazo: {db.data_br(t['prazo'])}")
    with st.container(border=True):
        st.markdown("#### 📋 O caso")
        st.markdown(md(t["caso"]))
    with st.container(border=True):
        st.markdown("#### 🚀 O desafio da turma")
        st.markdown(f"**{md(t['pergunta'])}**")
        st.markdown(f"**📦 O que você vai entregar ao final:** {md(t['entrega'])}")
        st.caption("Não existe resposta certa: o que vale é a sua leitura da situação e a sua criatividade.")
    st.markdown("**Competências que você vai desenvolver nesta trilha**")
    st.markdown("\n".join(f"- {md(c)}" for c in t.get("competencias") or []))


def mostrar_etapa(etapa: dict, indice: int) -> None:
    st.markdown(f"#### Etapa {indice + 1}: {md(etapa['titulo'])}")
    if etapa.get("competencia"):
        st.caption(f"Competência: {etapa['competencia']}")
    st.markdown(md(etapa["conteudo"]))
    if etapa.get("exemplo"):
        st.info(f"**Exemplo na prática:** {md(etapa['exemplo'])}", icon="💡")
    if etapa.get("recursos"):
        st.markdown("**Para aprofundar** (indicados pela área de T&D)")
        st.markdown("\n".join(f"- [{md(r['titulo'])}]({r['url']})" for r in etapa["recursos"]))
    st.markdown(f"**🤔 Reflexão aplicada ao caso:** {md(etapa['reflexao'])}")


def mostrar_mentoria(fb: dict) -> None:
    if fb.get("evolucao"):
        st.success(f"**📈 Como sua ideia evoluiu:** {md(fb['evolucao'])}")
    secoes = [("✨ O que é promissor na sua ideia", "pontos_promissores"),
              ("📚 Conexões com a trilha", "conexoes_com_a_trilha"),
              ("❓ Perguntas para fortalecer a proposta", "perguntas_para_fortalecer")]
    for titulo, chave in secoes:
        if fb.get(chave):
            st.markdown(f"**{titulo}**")
            st.markdown("\n".join(f"- {md(item)}" for item in fb[chave]))
    if fb.get("proximo_passo"):
        st.info(f"**👣 Sugestão de primeiro passo:** {md(fb['proximo_passo'])}")
    if fb.get("competencias_aplicadas"):
        st.caption("Competências que sua proposta mobiliza: " + " · ".join(fb["competencias_aplicadas"]))


def mostrar_proposta(p: dict) -> None:
    st.markdown("**Leitura do problema**")
    st.markdown(md(p["leitura"]))
    st.markdown("**Proposta**")
    st.markdown(md(p["proposta"]))


def _prefixo(t: dict) -> str:
    return seguranca.PREFIXO_TRAVADO if t["bloquear_colar"] else "✍️ "


# --- Página ---
def pagina() -> None:
    usuario = st.session_state["usuario"]
    st.title("🧭 Minhas trilhas")

    disponiveis = [t for t in db.listar_trilhas(status=["publicada", "encerrada"])
                   if t["status"] == "publicada" or t.get("devolutiva_em")]
    if not disponiveis:
        st.info("ℹ️ Nenhuma trilha aberta no momento. Quando seu gestor publicar uma, ela aparecerá aqui.")
        return

    rotulos = {t["id"]: t["titulo"] + ("" if t["status"] == "publicada" else " (encerrada)") for t in disponiveis}
    try:
        pedida = int(st.query_params.get("trilha", 0))
    except (TypeError, ValueError):
        pedida = 0
    ids = list(rotulos)
    tid = st.selectbox("Trilha", ids, index=ids.index(pedida) if pedida in ids else 0, format_func=rotulos.get)
    if st.query_params.get("trilha") != str(tid):
        st.query_params["trilha"] = str(tid)
    t = db.obter_trilha(tid)

    if usuario["sso"]:
        pid, nome = usuario["id"], usuario["nome"]
        st.caption(f"Participando como **{nome}**")
    else:
        with st.container(border=True):
            st.markdown("**Identificação**")
            c1, c2 = st.columns(2)
            nome = seguranca.sanitizar(c1.text_input("Nome", key="ident_nome", max_chars=120), 120)
            pid = seguranca.normalizar_id(c2.text_input("Matrícula ou e-mail corporativo", key="ident_mat", max_chars=120))
    if not pid or not nome:
        mostrar_caso(t)
        st.info("Informe seu nome e sua matrícula (ou e-mail corporativo) para participar.")
        return

    aberta = t["status"] == "publicada" and not db.prazo_vencido(t)
    feitas = db.progresso_participante(t["id"], pid)
    versoes = db.propostas_participante(t["id"], pid)
    total = len(t["etapas"])
    concluidas = sum(1 for i in range(total) if i in feitas)

    st.progress((concluidas + (1 if versoes else 0)) / (total + 1),
                text=f"{concluidas} de {total} etapas concluídas · proposta {'enviada' if versoes else 'pendente'}")
    if t["bloquear_colar"] and aberta:
        seguranca.bloquear_colar()

    abas = st.tabs(["📋 Caso", f"📚 Etapas ({concluidas}/{total})", "✍️ Minha proposta", "💬 Mural da turma", "📣 Devolutiva"])
    with abas[0]:
        mostrar_caso(t)
    with abas[1]:
        _etapas(t, pid, nome, feitas, aberta)
    with abas[2]:
        _proposta(t, pid, nome, versoes, concluidas == total, aberta)
    with abas[3]:
        _mural(t, pid, nome, versoes, aberta)
    with abas[4]:
        _devolutiva(t, versoes)


def _etapas(t: dict, pid: str, nome: str, feitas: dict, aberta: bool) -> None:
    st.caption("As etapas abrem em sequência: conclua a reflexão de uma para liberar a próxima.")
    proxima = next((i for i in range(len(t["etapas"])) if i not in feitas), None)
    for i, etapa in enumerate(t["etapas"]):
        if i in feitas:
            with st.expander(f"✅ Etapa {i + 1}: {etapa['titulo']}"):
                mostrar_etapa(etapa, i)
                st.markdown("**Sua reflexão**")
                st.markdown(md(feitas[i]["reflexao"]))
        elif i == proxima:
            with st.container(border=True):
                mostrar_etapa(etapa, i)
                if not aberta:
                    st.caption("A trilha está encerrada.")
                    continue
                with st.form(f"etapa_{t['id']}_{i}"):
                    texto = st.text_area(_prefixo(t) + "Sua reflexão", height=140, max_chars=1500,
                                         placeholder="Relacione o conteúdo ao caso e à realidade da sua equipe.")
                    concluir = st.form_submit_button("Concluir etapa", type="primary")
                if concluir:
                    texto = seguranca.sanitizar(texto, 1500)
                    if len(texto) < config.MIN_CHARS_REFLEXAO:
                        st.error(f"Escreva sua reflexão com pelo menos {config.MIN_CHARS_REFLEXAO} caracteres.")
                    else:
                        db.concluir_etapa(t["id"], pid, nome, i, texto)
                        db.auditar(seguranca.pseudonimo(pid), "etapa_concluida", f"trilha={t['id']} etapa={i + 1}")
                        st.toast(f"Etapa {i + 1} concluída!", icon="✅")
                        st.rerun()
        else:
            st.markdown(f"🔒 **Etapa {i + 1}: {md(etapa['titulo'])}** — abre quando você concluir a etapa anterior.")
    if proxima is None:
        st.success("Você concluiu todas as etapas. Agora é hora de propor sua solução, na aba **Minha proposta**.")


def _proposta(t: dict, pid: str, nome: str, versoes: list[dict], etapas_ok: bool, aberta: bool) -> None:
    if not etapas_ok and not versoes:
        st.info("Conclua as etapas de conteúdo para liberar sua proposta. Elas trazem o que você vai precisar.", icon="🔒")
        return
    st.markdown(f"**Entrega esperada:** {md(t['entrega'])}")
    for v in versoes:
        with st.expander(f"Versão {v['versao']} · {db.data_br(v['criado_em'])}", expanded=v is versoes[-1]):
            mostrar_proposta(v)
            if v.get("resposta_provocacao"):
                st.markdown(f"**Sua reflexão sobre a pergunta provocativa:** {md(v['resposta_provocacao'])}")
            st.divider()
            st.markdown("### 🤝 Mentoria")
            mostrar_mentoria(v["feedback"])

    if st.session_state.pop("proposta_enviada", False):
        st.toast("Mentoria pronta! O mural da turma já está aberto para você.", icon="💡")
    if not aberta:
        return
    if len(versoes) >= t["max_versoes"]:
        st.success("🎉 Proposta concluída. Continue contribuindo com os colegas no mural.")
        return
    _formulario_proposta(t, pid, nome, versoes)


def _formulario_proposta(t: dict, pid: str, nome: str, versoes: list[dict]) -> None:
    numero = len(versoes) + 1
    anterior = versoes[-1] if versoes else None
    provocacao = anterior["feedback"].get("pergunta_provocativa") if anterior else ""
    chave_inicio = f"inicio_{t['id']}_{pid}_{numero}"
    st.session_state.setdefault(chave_inicio, time.time())

    if numero == 1:
        st.markdown("### ✍️ Sua proposta")
    else:
        st.markdown(f"### 🔁 Lapidar a proposta — versão {numero} de {t['max_versoes']}")
        st.markdown("Aproveite o que fizer sentido da mentoria e dos comentários dos colegas. A ideia continua sendo sua.")

    prefixo = _prefixo(t)
    with st.form(f"proposta_{t['id']}_{numero}"):
        leitura = st.text_area(prefixo + "Como você enxerga o problema na sua equipe?", height=110, max_chars=1200,
                               value=anterior["leitura"] if anterior else "",
                               placeholder="O que você observa, quais são as causas prováveis e quem é afetado.")
        proposta = st.text_area(prefixo + "Sua proposta de solução", height=260, max_chars=t["limite_chars"],
                                value=anterior["proposta"] if anterior else "",
                                placeholder="O que você propõe, como usaria o que aprendeu nas etapas e como começaria.")
        resposta_provocacao = ""
        if provocacao:
            st.markdown(f"**🤔 Pergunta provocativa da mentoria:** {md(provocacao)}")
            resposta_provocacao = st.text_area(prefixo + "Sua reflexão sobre a pergunta provocativa", height=110, max_chars=800)
        declaracao = st.checkbox("Declaro que esta proposta é de minha autoria e reflete a minha visão sobre a equipe.")
        enviar = st.form_submit_button("Enviar e receber mentoria", type="primary")

    avisos = ["o tempo de elaboração é registrado"]
    if t["bloquear_colar"]:
        avisos.insert(0, "os campos não aceitam colar texto")
    st.caption(f"🔒 Para valorizar a autoria, {' e '.join(avisos)}. Seu nome não é enviado à IA. "
               "Ao enviar, sua proposta passa a aparecer no mural da turma.")
    if not enviar:
        return

    leitura = seguranca.sanitizar(leitura, 1200)
    proposta = seguranca.sanitizar(proposta, t["limite_chars"])
    resposta_provocacao = seguranca.sanitizar(resposta_provocacao, 800)
    if len(leitura) < 40:
        st.error("Conte um pouco mais sobre como você enxerga o problema.")
        return
    if len(proposta) < config.MIN_CHARS_PROPOSTA:
        st.error(f"Desenvolva um pouco mais a sua proposta (mínimo de {config.MIN_CHARS_PROPOSTA} caracteres).")
        return
    if provocacao and len(resposta_provocacao) < 30:
        st.error("Compartilhe sua reflexão sobre a pergunta provocativa antes de enviar.")
        return
    if not declaracao:
        st.error("Confirme a declaração de autoria para enviar.")
        return
    if db.contar_mentorias_hoje(pid) >= config.MAX_MENTORIAS_DIA:
        st.error("Você atingiu o limite diário de mentorias. Tente novamente amanhã.")
        return

    tempo = int(time.time() - st.session_state[chave_inicio])
    ja_existia = len(anterior["leitura"]) + len(anterior["proposta"]) if anterior else 0
    digitado = max(len(leitura) + len(proposta) - ja_existia, 0) + len(resposta_provocacao)
    ritmo = digitado / max(tempo / 60, 0.1)

    with st.spinner("A mentoria está analisando sua ideia à luz da trilha..."):
        try:
            feedback = ia.mentorar_proposta(t, leitura, proposta, resposta_provocacao, anterior)
        except ia.ErroIA as erro:
            st.error(str(erro))
            return

    db.registrar_proposta(dict(
        trilha_id=t["id"], participante_id=pid, participante_nome=nome, versao=numero, leitura=leitura,
        proposta=proposta, resposta_provocacao=resposta_provocacao or None, feedback=feedback,
        tempo_segundos=tempo, ritmo_atipico=ritmo > config.RITMO_ATIPICO_CPM,
        status_ideia=(anterior or {}).get("status_ideia") or "nova",
    ))
    db.auditar(seguranca.pseudonimo(pid), "proposta_enviada", f"trilha={t['id']} versao={numero}")
    st.session_state.pop(chave_inicio, None)
    st.session_state["proposta_enviada"] = True
    st.rerun()


def _mural(t: dict, pid: str, nome: str, versoes: list[dict], aberta: bool) -> None:
    atuais = db.propostas_atuais(t["id"])
    if not versoes:
        st.info(f"O mural abre depois que você enviar a primeira versão da sua proposta, para que cada pessoa "
                f"construa a sua ideia antes de conhecer as dos colegas. Propostas no mural: {len(atuais)}.", icon="🔒")
        return

    comentarios = db.listar_comentarios(t["id"])
    por_alvo: dict[str, list[dict]] = {}
    for c in comentarios:
        por_alvo.setdefault(c["alvo_id"], []).append(c)

    st.caption("Leia as propostas dos colegas e contribua com perguntas, ideias e conexões com a trilha. "
               "Comentários respeitosos e construtivos: o mural é um espaço de colaboração, não de avaliação.")
    minha = next((p for p in atuais if p["participante_id"] == pid), None)
    ordem = ([minha] if minha else []) + sorted((p for p in atuais if p["participante_id"] != pid),
                                               key=lambda p: p["criado_em"], reverse=True)
    for p in ordem:
        propria = p["participante_id"] == pid
        recebidos = por_alvo.get(p["participante_id"], [])
        titulo = "Sua proposta" if propria else p["participante_nome"]
        resumo = p["feedback"].get("sintese") or p["proposta"][:100]
        with st.expander(f"{'⭐ ' if propria else ''}{titulo} — {resumo} · 💬 {len(recebidos)}", expanded=propria and bool(recebidos)):
            mostrar_proposta(p)
            if p["feedback"].get("competencias_aplicadas"):
                st.caption("Competências mobilizadas: " + " · ".join(p["feedback"]["competencias_aplicadas"]))
            for c in recebidos:
                st.markdown(f"> **{md(c['autor_nome'])}** · {db.data_br(c['criado_em'])}  \n> {md(c['texto'])}")
            if aberta and not propria:
                with st.form(f"comentar_{t['id']}_{p['participante_id']}", clear_on_submit=True):
                    texto = st.text_area("Seu comentário", max_chars=800, height=80,
                                         placeholder="Uma pergunta, uma ideia para somar ou uma conexão com as etapas.")
                    if st.form_submit_button("Comentar"):
                        texto = seguranca.sanitizar(texto, 800)
                        if len(texto) < 15:
                            st.error("Escreva um comentário um pouco mais completo.")
                        else:
                            db.comentar(t["id"], p["participante_id"], pid, nome, texto)
                            db.auditar(seguranca.pseudonimo(pid), "comentario_mural", f"trilha={t['id']}")
                            st.rerun()


def _devolutiva(t: dict, versoes: list[dict]) -> None:
    if not t.get("devolutiva"):
        st.info("A devolutiva do gestor para a turma aparecerá aqui quando a trilha for concluída.", icon="⏳")
        return
    with st.container(border=True):
        st.markdown("#### 📣 Devolutiva do gestor para a turma")
        st.markdown(md(t["devolutiva"]))
        st.caption(db.data_br(t.get("devolutiva_em")))
    if versoes:
        status = versoes[-1].get("status_ideia") or "nova"
        if status != "nova":
            st.markdown(f"**Encaminhamento da sua ideia:** {db.STATUS_IDEIA.get(status, status)}")
