"""Data models for subtitle processing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubtitleEntry:
    """Represents a single subtitle entry with timing and text."""
    index: int
    start: float  # seconds
    end: float  # seconds
    text: str
