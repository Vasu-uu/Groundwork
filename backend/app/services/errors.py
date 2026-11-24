"""Domain errors with user-facing messages. The API maps them to HTTP status codes."""

from __future__ import annotations


class DomainError(Exception):
    """Base class. `code` is a stable machine-readable identifier for the UI."""

    code = "error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(DomainError):  # -> 404
    code = "not_found"


class InvalidInputError(DomainError):  # -> 422
    code = "invalid_input"


class ConflictError(DomainError):  # -> 409: not allowed in the current state
    code = "conflict"


class CheckpointError(ConflictError):  # -> 409: the human checkpoint has not been passed
    code = "checkpoint_required"
