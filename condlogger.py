"""Logging facility for the conditionals preprocessor."""

from enum import Enum
from typing import Optional


class Severity(Enum):
    """Severity levels for conditional processing issues."""
    DISCOURAGED = "DISCOURAGED"
    UNSUPPORTED = "UNSUPPORTED"
    FORMAT = "FORMAT"
    FATAL = "FATAL"
    BUG = "BUG"


class CondLogger:
    """Logger for tracking issues found during conditional preprocessing."""

    def __init__(self, filename: str, stdout: bool = False):
        """Initialize the logger.

        Args:
            filename: The source file being processed
            stdout: Whether to output log messages to stdout
        """
        self.filename = filename
        self.stdout = stdout
        self.entries = []

    def log(self, severity: Severity, start_line: int,
            end_line: Optional[int] = None, message: str = ""):
        """Log an issue.

        Args:
            severity: The severity level
            start_line: Starting line number
            end_line: Optional ending line number
            message: Description of the issue
        """
        entry = {
            "severity": severity.value,
            "start_line": start_line,
            "message": message
        }

        if end_line is not None:
            entry["end_line"] = end_line

        self.entries.append(entry)

        if self.stdout:
            line_range = str(start_line)
            if end_line is not None:
                line_range += f"-{end_line}"
            print(f"{self.filename}:{severity.value}:{line_range}:{message}")

    def get_entries(self):
        """Return all logged entries for serialization."""
        return self.entries
