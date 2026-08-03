class DocumentError(Exception):
    """Base exception for document operations."""


class DocumentNotFoundError(DocumentError):
    """Raised when a document or owned course cannot be found."""


class UnsupportedFileTypeError(DocumentError):
    """Raised when the uploaded file type is not allowed."""


class FileTooLargeError(DocumentError):
    """Raised when the uploaded file exceeds the configured size limit."""


class DuplicateDocumentError(DocumentError):
    """Raised when the same file already exists in the target course."""


class FileStorageError(DocumentError):
    """Raised when the physical file cannot be stored or removed."""