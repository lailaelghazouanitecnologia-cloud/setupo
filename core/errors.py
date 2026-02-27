class SetupoError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(SetupoError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} '{resource_id}' not found", 404)


class ConflictError(SetupoError):
    def __init__(self, message: str):
        super().__init__(message, 409)


class ProviderError(SetupoError):
    def __init__(self, provider: str, message: str):
        super().__init__(f"[{provider}] {message}", 502)


class AuthError(SetupoError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, 401)


class ValidationError(SetupoError):
    def __init__(self, message: str):
        super().__init__(message, 422)
