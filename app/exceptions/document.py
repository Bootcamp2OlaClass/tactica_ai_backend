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

class DocumentFileMissingError(DocumentError, LookupError):
    """Raised when document metadata exists but the physical file is missing."""

class DocumentReprocessNotAllowedError(DocumentError):
    """Raised when a document's current processing_status doesn't allow
    reprocessing (e.g. already QUEUED/PROCESSING/COMPLETED)."""

class DocumentProcessingUnavailableError(DocumentError):
    """Raised when a document is otherwise eligible for reprocessing but
    the job could not be enqueued (e.g. the broker is unreachable)."""