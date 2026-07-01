"""Custom exception types for PDF parsing, classification, and compression errors."""


class PDFParseError(Exception):
    """Raised when PDF input cannot be opened, rendered, or written."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ClassificationError(Exception):
    """Raised when page feature extraction or classification fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CompressionError(Exception):
    """Raised when page compression or binary search compression fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
