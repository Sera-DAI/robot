"""Aplicação: liga as regras do domínio aos adaptadores. Fina, sem regra de negócio própria."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .dominio import alexa, comandos
from .erros import (
    ArmazenamentoErro,
    FilaErro,
    GatewayErro,
    InvocacaoErro,
    LwaErro,
)

LOG = logging.getLogger(__name__)

MARGEM_RENOVACAO_S = 60
CHAVE_INTERNA = "robot_interno"


class Tokens(Protocol):
    def obter(self) -> dict[str, Any] | None: ...
    def salvar(self, registro: dict[str, Any]) -> None: ...


class Lwa(Protocol):
    def trocar_codigo(self, codigo: str) -> dict[str, Any]: ...
    def renovar(self, refresh_token: str) -> dict[str, Any]: ...


class Gateway(Protocol):
    def enviar(self, evento: dict[str, Any]) -> None: ...


class Invocador(Protocol):
    def disparar(self, carga: dict[str, Any]) -> None: ...


class Fila(Protocol):
    def enviar(self, comando: dict[str, Any]) -> None: ...


@dataclass
class Config:
    endpoint_id: str
    mac: str


@dataclass
class Deps:
    config: Config
    tokens: Tokens
    lwa: Lwa
    gateway: Gateway
    invocador: Invocador
    fila: Fila
    agora: Callable[[], float]  # segundos desde a época
    agora_iso: Callable[[], str]
    novo_id: Callable[[], str]


def processar(evento: dict[str, Any], d: Deps) -> dict[str, Any]:
    """Ponto de entrada. Só o log de rota é registrado: nunca o evento, que carrega token."""
    if isinstance(evento, dict) and "directive" not in evento and CHAVE_INTERNA in evento:
        return _processar_interno(evento[CHAVE_INTERNA], d)
    try:
        diretiva = alexa.separar(evento)
    except ValueError:
        LOG.warning("evento descartado: formato inválido")
        return alexa.erro_sincrono(None, None, d.novo_id(), alexa.ERRO_DIRETIVA_INVALIDA, "Diretiva inválida")

    LOG.info("diretiva recebida: %s", diretiva.rota)
    if diretiva.rota == alexa.ROTA_DISCOVERY:
        try:
            return alexa.discovery(d.config.endpoint_id, d.config.mac, d.novo_id())
        except ValueError:
            LOG.error("Discovery falhou: MAC configurado fora do formato esperado")
            return alexa.erro_sincrono(None, None, d.novo_id(), alexa.ERRO_INTERNO, "Configuração inválida")
    if diretiva.rota == alexa.ROTA_ACCEPT_GRANT:
        return _aceitar_grant(diretiva, d)
    if diretiva.rota == alexa.ROTA_LIGAR:
        return _ligar(diretiva, d)
    if diretiva.rota == alexa.ROTA_DESLIGAR:
        return _desligar(diretiva, d)
    return alexa.erro_sincrono(
        diretiva.endpoint_id, diretiva.correlation_token, d.novo_id(),
        alexa.ERRO_DIRETIVA_INVALIDA, "Diretiva não suportada",
    )


def _aceitar_grant(diretiva: alexa.Diretiva, d: Deps) -> dict[str, Any]:
    try:
        codigo = alexa.extrair_codigo_grant(diretiva.payload)
        dados = d.lwa.trocar_codigo(codigo)
        d.tokens.salvar(_registro(dados, d.agora()))
    except (ValueError, LwaErro, ArmazenamentoErro) as erro:
        LOG.error("AcceptGrant falhou: %s", type(erro).__name__)
        return alexa.accept_grant_erro(d.novo_id())
    return alexa.accept_grant_ok(d.novo_id())


def _ligar(diretiva: alexa.Diretiva, d: Deps) -> dict[str, Any]:
    if diretiva.endpoint_id != d.config.endpoint_id:
        return alexa.erro_sincrono(
            diretiva.endpoint_id, diretiva.correlation_token, d.novo_id(),
            alexa.ERRO_ENDPOINT_INEXISTENTE, "Dispositivo desconhecido",
        )
    try:
        d.invocador.disparar(
            {
                CHAVE_INTERNA: {
                    "acao": "ligar",
                    "endpointId": diretiva.endpoint_id,
                    "correlationToken": diretiva.correlation_token,
                }
            }
        )
    except InvocacaoErro as erro:
        LOG.error("TurnOn falhou ao agendar os eventos: %s", type(erro).__name__)
        return alexa.erro_sincrono(
            diretiva.endpoint_id, diretiva.correlation_token, d.novo_id(),
            alexa.ERRO_INTERNO, "Falha ao iniciar o comando",
        )
    return alexa.deferred(diretiva.correlation_token, d.novo_id())


def _desligar(diretiva: alexa.Diretiva, d: Deps) -> dict[str, Any]:
    """Põe o comando na fila e responde na hora. Quem desliga é o agente do PC."""
    if diretiva.endpoint_id != d.config.endpoint_id:
        return alexa.erro_sincrono(
            diretiva.endpoint_id, diretiva.correlation_token, d.novo_id(),
            alexa.ERRO_ENDPOINT_INEXISTENTE, "Dispositivo desconhecido",
        )
    try:
        d.fila.enviar(comandos.montar(comandos.ACAO_DESLIGAR))
    except FilaErro as erro:
        LOG.error("TurnOff falhou ao enviar o comando para a fila: %s", type(erro).__name__)
        return alexa.erro_sincrono(
            diretiva.endpoint_id, diretiva.correlation_token, d.novo_id(),
            alexa.ERRO_INTERNO, "Falha ao enviar o comando",
        )
    LOG.info("TurnOff: comando de desligar enviado para a fila")
    return alexa.resposta_sincrona(
        diretiva.endpoint_id, diretiva.token_usuario, diretiva.correlation_token,
        d.novo_id(), "OFF", d.agora_iso(),
    )


def _processar_interno(carga: Any, d: Deps) -> dict[str, Any]:
    """Segunda invocação, assíncrona: envia WakeUp e a Response final ao gateway."""
    if not isinstance(carga, dict) or carga.get("acao") != "ligar":
        LOG.warning("invocação interna descartada: ação desconhecida")
        return {"ok": False, "motivo": "acao_desconhecida"}
    endpoint_id = carga.get("endpointId")
    correlation = carga.get("correlationToken")
    if endpoint_id != d.config.endpoint_id:
        LOG.warning("invocação interna descartada: endpoint desconhecido")
        return {"ok": False, "motivo": "endpoint_desconhecido"}

    try:
        token = _token_valido(d)
    except (LwaErro, ArmazenamentoErro) as erro:
        LOG.error("sem token para enviar eventos: %s", type(erro).__name__)
        return {"ok": False, "motivo": "sem_token"}
    if token is None:
        LOG.error("sem token para enviar eventos: AcceptGrant ainda não concluído")
        return {"ok": False, "motivo": "sem_token"}

    try:
        d.gateway.enviar(alexa.evento_wakeup(token, endpoint_id, correlation, d.novo_id(), d.agora_iso()))
        d.gateway.enviar(alexa.evento_resposta(token, endpoint_id, correlation, d.novo_id(), d.agora_iso()))
    except GatewayErro as erro:
        LOG.error("envio de eventos falhou: %s", type(erro).__name__)
        _tentar_enviar_erro(token, endpoint_id, correlation, d)
        return {"ok": False, "motivo": "gateway"}
    LOG.info("TurnOn: WakeUp e Response enviados ao gateway")
    return {"ok": True}


def _tentar_enviar_erro(token: str, endpoint_id: str, correlation: str | None, d: Deps) -> None:
    try:
        d.gateway.enviar(
            alexa.evento_erro(token, endpoint_id, correlation, d.novo_id(), alexa.ERRO_INTERNO, "Falha ao ligar o PC")
        )
    except GatewayErro:
        LOG.error("não foi possível avisar a Alexa do erro")


def _token_valido(d: Deps) -> str | None:
    registro = d.tokens.obter()
    if registro is None:
        return None
    if registro["expira_em"] - d.agora() > MARGEM_RENOVACAO_S:
        return registro["access_token"]
    novos = d.lwa.renovar(registro["refresh_token"])
    d.tokens.salvar(_registro(novos, d.agora(), refresh_anterior=registro["refresh_token"]))
    return novos["access_token"]


def _registro(dados: dict[str, Any], agora: float, refresh_anterior: str | None = None) -> dict[str, Any]:
    return {
        "access_token": dados["access_token"],
        "refresh_token": dados.get("refresh_token") or refresh_anterior,
        "expira_em": int(agora) + int(dados["expires_in"]),
    }
