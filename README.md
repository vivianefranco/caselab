# CaseLab — aprender resolvendo um problema real da equipe

O CaseLab apoia uma equipe a **desenvolver as competências de que precisa para resolver um problema real
da própria área**, por meio de uma trilha de aprendizagem que começa pelo caso.

O gestor traz o problema. A IA rascunha a trilha a partir dos materiais da biblioteca e a área de T&D revisa
e aprova. A turma aprende em etapas curtas, propõe soluções com mentoria da IA e troca ideias num mural.
O gestor recebe uma síntese e fecha com uma devolutiva coletiva. **Não há nota nem resposta certa.**

## Papéis

| Papel | O que faz |
|---|---|
| Área de T&D | Mantém a biblioteca de materiais; revisa, ajusta e aprova as trilhas; indica recursos complementares |
| Gestor | Registra o problema, quem participa e as competências necessárias; publica; encaminha ideias; faz a devolutiva coletiva |
| Colaborador | Percorre as etapas, propõe uma solução, lapida a ideia e comenta as propostas dos colegas |
| IA | Rascunha a trilha, faz a mentoria individual e sintetiza a turma — sempre com revisão humana |

## Fluxo

1. **Nova trilha** (gestor): problema → quem (cargo/função e contexto) → competências (a IA pode sugerir) → materiais.
2. **Rascunho** (IA): caso, convite, entrega esperada (definida a partir do caso) e 3 a 5 etapas — cada uma com
   conteúdo, exemplo e reflexão aplicada ao caso. A complexidade segue o cargo/função; não há "nível de dificuldade".
3. **Revisão** (T&D): edita tudo, inclui recursos (`Título | https://...`), registra observações e aprova ou devolve.
4. **Publicação** (gestor): link da trilha e aviso coletivo opcional no Teams.
5. **Trilha** (colaborador): etapas liberadas em sequência → proposta com mentoria → mural (abre após a primeira
   versão) → nova versão, se quiser → devolutiva.
6. **Fechamento** (gestor): andamento por etapa, competências mobilizadas, encaminhamento das ideias, síntese da
   turma pela IA e devolutiva coletiva (com rascunho sugerido). Retornos individuais vêm da mentoria e dos colegas.

## Estrutura

```
app.py                      # entrada: login, papéis, navegação
caselab/config.py           # Secrets/.env, limites, revisão da T&D ativa ou não
caselab/db.py               # SQLAlchemy (SQLite local ou PostgreSQL)
caselab/ia.py               # prompts: competências, trilha, mentoria, síntese
caselab/conteudo.py         # extração de texto (PDF, DOCX, PPTX) e seleção de trechos (BM25)
caselab/seguranca.py        # autenticação, papéis, higienização, bloqueio de colar
caselab/teams.py            # avisos coletivos no Teams (Workflows)
caselab/telas/inicio.py     # objetivo, percurso e papéis
caselab/telas/colaborador.py# trilha do colaborador: caso, etapas, proposta, mural, devolutiva
caselab/telas/trilhas.py    # criar, revisar, aprovar e publicar
caselab/telas/turma.py      # acompanhar, encaminhar, síntese e devolutiva coletiva
caselab/telas/biblioteca.py # materiais de referência
```

## Rodar localmente

```bash
pip install -r requirements.txt
mkdir -p .streamlit && cp secrets.toml.exemplo .streamlit/secrets.toml   # e preencha
streamlit run app.py
```

## Deploy no Streamlit Community Cloud

1. Suba o projeto no GitHub (renomeie `gitignore.txt` para `.gitignore`; nunca suba `.env` nem `secrets.toml`).
2. Em share.streamlit.io, crie o app apontando para `app.py`.
3. Em **Settings → Secrets**, cole o conteúdo de `secrets.toml.exemplo` preenchido.
4. Defina `APP_URL` com a URL pública do app.
5. Para não perder dados quando o app reinicia, configure `DATABASE_URL` com um PostgreSQL (Supabase, Neon…).

## Segurança e privacidade

| Tema | Medida |
|---|---|
| Autenticação | SSO corporativo via OIDC (Microsoft Entra ID) com `st.login`; papéis por `GESTORES_EMAILS` e `TD_EMAILS`; restrição por `DOMINIOS_PERMITIDOS`. Demonstração: `GESTOR_SENHA` e `TD_SENHA`, comparação em tempo constante, bloqueio após 5 tentativas. |
| Autorização | Menus por papel e checagem em cada tela; T&D aprova, gestor publica; trilha publicada fica travada. |
| Revisão humana | Nenhum conteúdo gerado pela IA chega à turma sem revisão (T&D, quando configurada). |
| Segredos | Chaves, senhas, banco e webhooks só nos Secrets. |
| Teams | Somente avisos coletivos; URLs cadastradas pela TI e validadas por domínio. |
| Links externos | Recursos aceitam apenas `https://`. |
| Injeção de prompt | Materiais e textos delimitados por tags; tags reservadas removidas; IA instruída a ignorar comandos nos dados; competências validadas contra a lista da trilha. |
| Minimização (LGPD) | Nome do colaborador nunca vai para a IA; síntese anônima. |
| Transparência (LGPD) | Aviso de privacidade diz quem vê o quê (reflexões: só a pessoa e gestores; propostas e comentários: também a turma). |
| Eliminação (LGPD) | Exclusão de reflexões, propostas e comentários de um participante; auditada com pseudônimo. |
| Auditoria | Tabela `auditoria`: logins, criação, revisão, aprovação, publicação, encaminhamentos, devolutiva, exportação, exclusões. |
| Abuso e custo | Limites de mentorias por pessoa/dia e de uso da IA por sessão; limites de upload e de tamanho. |
| Banco e exportação | Consultas parametrizadas; CSV protegido contra injeção de fórmulas. |

### Pontos para a TI avaliar antes de uso real

- **Provedor de IA:** o Qwen (Alibaba Cloud) processa os dados fora do Brasil. Para uso corporativo, prefira um
  provedor homologado — basta trocar `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY`.
- **Hospedagem:** o Streamlit Community Cloud serve ao protótipo; em produção, infraestrutura da organização.
- **Banco de dados:** as tabelas mudaram em relação às versões anteriores; apague `caselab.db` se tiver uma cópia antiga.
