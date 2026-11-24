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
