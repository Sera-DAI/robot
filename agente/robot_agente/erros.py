"""Erros do agente. As mensagens nunca carregam chave, segredo nem corpo de resposta."""


class AgenteErro(Exception):
    """Base dos erros esperados."""


class CredencialErro(AgenteErro):
    """A credencial não está no Credential Manager ou não pôde ser lida."""


class ConfigErro(AgenteErro):
    """Arquivo de configuração ausente ou inválido."""


class FilaErro(AgenteErro):
    """Falha ao falar com a fila SQS."""


class DesligamentoErro(AgenteErro):
    """O Windows recusou o comando de desligar."""
