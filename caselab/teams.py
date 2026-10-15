"""Avisos coletivos no Microsoft Teams via Workflows (webhook).

O Teams recebe apenas avisos para a turma (trilha publicada, devolutiva disponível).
Retornos individuais ficam dentro do CaseLab, visíveis só para a própria pessoa.
As URLs de webhook ficam nos Secrets (configuradas pela TI), nunca digitadas na tela.
"""
from urllib.parse import urlparse

import requests

from . import config

_DOMINIOS_PERMITIDOS = (
    ".logic.azure.com",
    ".powerplatform.com",
    ".powerautomate.com",
    ".webhook.office.com",
)


def url_valida(url: str) -> bool:
    try:
        partes = urlparse(url)
    except ValueError:
        return False
    host = (partes.hostname or "").lower()
    return partes.scheme == "https" and host.endswith(_DOMINIOS_PERMITIDOS)


def link_trilha(tid: int) -> str:
    return f"{config.APP_URL}/trilhas?trilha={tid}"


def avisar(url: str, titulo: str, blocos: list[tuple[str, str]], botao: str, link: str) -> tuple[bool, str]:
    if not url or not url_valida(url):
        return False, "URL do canal do Teams inválida ou fora dos domínios permitidos."

    corpo = [{"type": "TextBlock", "text": titulo, "weight": "Bolder", "size": "Medium", "wrap": True}]
    for rotulo, texto in blocos:
        if rotulo:
            corpo.append({"type": "TextBlock", "text": rotulo, "weight": "Bolder", "spacing": "Medium", "wrap": True})
        if texto:
            corpo.append({"type": "TextBlock", "text": texto[:1500], "wrap": True})

    cartao = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": corpo,
                "actions": [{"type": "Action.OpenUrl", "title": botao, "url": link}],
            },
        }],
    }
    try:
        resposta = requests.post(url, json=cartao, timeout=20)
    except requests.RequestException:
        return False, "Não foi possível conectar ao Teams."
    if resposta.status_code in (200, 202):
        return True, "Aviso enviado ao canal do Teams."
    return False, f"O Teams recusou o aviso (status {resposta.status_code})."
