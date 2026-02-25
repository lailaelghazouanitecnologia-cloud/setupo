"""MMS Errors - Custom exceptions for the platform."""


class MmsError(Exception):
    """Base error for all MMS errors."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# Keep backward compat alias
SetupoError = MmsError


class NotFoundError(MmsError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} '{resource_id}' not found", 404)


class ConflictError(MmsError):
    def __init__(self, message: str):
        super().__init__(message, 409)


class ProviderError(MmsError):
    def __init__(self, provider: str, message: str):
        super().__init__(f"[{provider}] {message}", 502)


class AuthError(MmsError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, 401)


class ValidationError(MmsError):
    def __init__(self, message: str):
        super().__init__(message, 422)
