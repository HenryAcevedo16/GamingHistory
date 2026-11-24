from app.core.errors import StudioError


class AIError(StudioError):
    code = "AI_FAILED"
    status_code = 502


class AICLINotFound(AIError):
    code = "AI_CLI_NOT_FOUND"
    status_code = 503


class AINotLoggedIn(AIError):
    code = "AI_NOT_LOGGED_IN"
    status_code = 503


class AITimeout(AIError):
    code = "AI_TIMEOUT"
    status_code = 504


class AIServerUnavailable(AIError):
    code = "AI_SERVER_UNAVAILABLE"
    status_code = 503


class AIAuthFailed(AIError):
    code = "AI_AUTH_FAILED"
    status_code = 503


class AIModelRequired(AIError):
    code = "AI_MODEL_REQUIRED"
    status_code = 422


class AIProviderUnavailable(AIError):
    code = "AI_PROVIDER_UNAVAILABLE"
    status_code = 503


class AIUnsupportedInput(AIError):
    code = "AI_MODEL_UNSUPPORTED_INPUT"
    status_code = 422


class AICancelled(AIError):
    code = "AI_CANCELLED"
    status_code = 499
