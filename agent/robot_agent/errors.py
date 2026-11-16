"""Agent errors. Messages never carry a key, a secret or a response body."""


class AgentError(Exception):
    """Base class of the expected errors."""


class CredentialError(AgentError):
    """The credential is not in the Credential Manager or could not be read."""


class ConfigError(AgentError):
    """Configuration file missing or invalid."""


class QueueError(AgentError):
    """Failure talking to the SQS queue."""


class ShutdownError(AgentError):
    """Windows refused the shutdown command."""
