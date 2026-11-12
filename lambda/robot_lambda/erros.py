"""Erros do projeto. As mensagens nunca carregam token, segredo nem corpo de resposta."""


class RobotErro(Exception):
    """Base dos erros esperados."""


class LwaErro(RobotErro):
    """Falha ao falar com o Login with Amazon."""


class GatewayErro(RobotErro):
    """Falha ao enviar evento ao gateway de eventos da Alexa."""


class InvocacaoErro(RobotErro):
    """Falha ao disparar a própria função de forma assíncrona."""


class ArmazenamentoErro(RobotErro):
    """Falha ao ler ou gravar os tokens."""


class FilaErro(RobotErro):
    """Falha ao enviar comando para a fila do agente."""
