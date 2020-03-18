class VcdException(Exception):
    """Base class for all vcd related Exceptions."""


class ClientException(Exception):
    """Base class for all exceptions arising in the client."""


class VcdResponseException(VcdException):
    """Base class for all vcd response related Exceptions."""
    def __init__(self, status_code, request_id, vcd_error):
        self.status_code = status_code
        self.request_id = request_id
        self.vcd_error = vcd_error

    def __str__(self):
        if self.vcd_error:
            error_message = 'Status code:%d/%s\n' % (
                self.status_code, self.vcd_error.minor_error_code)
            error_message += 'Message: %s\n' % self.vcd_error.message
            error_message += 'Request Id: %s\n' % self.request_id
            stack_trace = self.vcd_error.stack_trace
            if stack_trace:
                error_message += 'Stack trace: %s\n' % stack_trace
        else:
            error_message = 'Status code: %d\n' % self.status_code
            error_message += '<empty response body>'
            error_message += 'Request Id: %s\n' % self.request_id

        return error_message


class VcdTaskException(VcdException):
    """Exception related to tasks in vcd."""
    def __init__(self, error_message, vcd_error):
        self.error_message = error_message
        self.vcd_error = vcd_error

    def __str__(self):
        return 'VcdTaskException; %s/%s: %s (%s)' % (
            self.vcd_error.major_error_code, self.vcd_error.minor_error_code,
            self.error_message, self.vcd_error.message)


class BadRequestException(VcdResponseException):
    """Raised when vcd returns 400 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(BadRequestException, self).__init__(status_code, request_id,
                                                  vcd_error)


class UnauthorizedException(VcdResponseException):
    """Raised when vcd returns 401 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(UnauthorizedException, self).__init__(status_code, request_id,
                                                    vcd_error)


class AccessForbiddenException(VcdResponseException):
    """Raised when vcd returns 403 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(AccessForbiddenException, self).__init__(status_code, request_id,
                                                       vcd_error)


class NotFoundException(VcdResponseException):
    """Raised when vcd returns 404 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(NotFoundException, self).__init__(status_code, request_id,
                                                vcd_error)


class MethodNotAllowedException(VcdResponseException):
    """Raised when vcd returns 405 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(MethodNotAllowedException,
              self).__init__(status_code, request_id, vcd_error)


class NotAcceptableException(VcdResponseException):
    """Raised when vcd returns 406 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(NotAcceptableException, self).__init__(status_code, request_id,
                                                     vcd_error)


class RequestTimeoutException(VcdResponseException):
    """Raised when vcd returns 408 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(RequestTimeoutException, self).__init__(status_code, request_id,
                                                      vcd_error)


class ConflictException(VcdResponseException):
    """Raised when vcd returns 409 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(ConflictException, self).__init__(status_code, request_id,
                                                vcd_error)


class UnsupportedMediaTypeException(VcdResponseException):
    """Raised when vcd returns 415 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(UnsupportedMediaTypeException,
              self).__init__(status_code, request_id, vcd_error)


class InvalidContentLengthException(VcdResponseException):
    """Raised when vcd returns 416 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(InvalidContentLengthException,
              self).__init__(status_code, request_id, vcd_error)


class InternalServerException(VcdResponseException):
    """Raised when vcd returns 500 response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(InternalServerException, self).__init__(status_code, request_id,
                                                      vcd_error)


class UnknownApiException(VcdResponseException):
    """Raised when vcd returns an unknown response code."""
    def __init__(self, status_code, request_id, vcd_error):
        super(UnknownApiException, self).__init__(status_code, request_id,
                                                  vcd_error)


class TaskTimeoutException(ClientException, TimeoutError):
    """Raised when a task in vcd timeout."""