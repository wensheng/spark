"""Exception-related type definitions for the ADK."""


class ContextWindowOverflowException(Exception):
    """Exception raised when the context window is exceeded.

    This exception is raised when the input to a model exceeds the maximum context window size that the model can
    handle. This typically occurs when the combined length of the conversation history, system prompt, and current
    message is too large for the model to process.
    """

    pass


class ModelThrottledException(Exception):
    """Exception raised when the model is throttled.

    This exception is raised when the model is throttled by the service. This typically occurs when the service is
    throttling the requests from the client.
    """

    def __init__(self, message: str) -> None:
        """Initialize exception.

        Args:
            message: The message from the service that describes the throttling.
        """
        self.message = message
        super().__init__(message)

    pass
