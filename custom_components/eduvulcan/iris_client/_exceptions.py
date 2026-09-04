class IrisApiException(Exception):
    """Base Iris API exception."""


class FailedRequestException(IrisApiException):
    """Request failed to execute."""


class HttpUnsuccessfullStatusException(IrisApiException):
    """HTTP status was not 200."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"{status_code}: {message}")


class ExpiredTokenException(IrisApiException):
    """Token expired."""


class WrongPINException(IrisApiException):
    """PIN invalid."""


class WrongTokenException(IrisApiException):
    """Token invalid."""


class UsedTokenException(IrisApiException):
    """Token already used."""


class InvalidHeaderException(IrisApiException):
    """Request header invalid."""


class MissingHeaderException(IrisApiException):
    """Required header missing."""


class InvalidBodyModelException(IrisApiException):
    """Request body invalid."""


class InvalidSignatureException(IrisApiException):
    """Signature invalid."""


class CertificateNotFoundException(IrisApiException):
    """Certificate not found."""


class EntityNotFoundException(IrisApiException):
    """Entity not found."""


class ConstraintViolationException(IrisApiException):
    """Constraint violated."""


class InvalidParameterValueException(IrisApiException):
    """Invalid parameter value."""


class MissingUnitSymbolException(IrisApiException):
    """Unit symbol missing."""


class InternalServerErrorException(IrisApiException):
    """Server error."""


class ResponseInvalidContentTypeException(IrisApiException):
    """Response content type invalid."""
