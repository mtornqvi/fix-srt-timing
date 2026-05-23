"""Logging utilities for subtitle processing."""

from __future__ import annotations

from pathlib import Path


# Global log file handle
_log_file = None


def log(message: str) -> None:
    """Write message to log file only."""
    if _log_file:
        _log_file.write(message + "\n")
        _log_file.flush()


def setup_logging(video_path: Path) -> Path:
    """Initialize logging to a file named after the video file."""
    global _log_file
    log_path = video_path.with_suffix(".log")
    _log_file = open(log_path, "w", encoding="utf-8")
    return log_path


def close_logging() -> None:
    """Close the log file."""
    global _log_file
    if _log_file:
        _log_file.close()
        _log_file = None


def get_log_file():
    """Get the current log file handle for error checking."""
    return _log_file
