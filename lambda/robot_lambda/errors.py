"""Project errors. Messages never carry a token, a secret or a response body."""


class RobotError(Exception):
    """Base class of the expected errors."""


class LwaError(RobotError):
    """Failure talking to Login with Amazon."""


class GatewayError(RobotError):
    """Failure sending an event to the Alexa event gateway."""


class InvocationError(RobotError):
    """Failure triggering the function itself asynchronously."""


class StorageError(RobotError):
    """Failure reading or writing the tokens."""


class QueueError(RobotError):
    """Failure sending a command to the agent's queue."""
