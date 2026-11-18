from fastapi import HTTPException, status

class AttendAIException(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)

class UnauthorizedException(AttendAIException):
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

class ForbiddenException(AttendAIException):
    def __init__(self, detail: str = "Insufficient permissions for requested resource"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

class NotFoundException(AttendAIException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class ConflictException(AttendAIException):
    def __init__(self, detail: str = "Conflict with existing resource"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)

class BadRequestException(AttendAIException):
    def __init__(self, detail: str = "Bad request parameters"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class ValidationException(AttendAIException):
    def __init__(self, detail: str = "Invalid request parameters"):
        super().__init__(status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422), detail=detail)
