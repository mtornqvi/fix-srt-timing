"""SRT file parsing and serialization."""

from __future__ import annotations

import re

from models import SubtitleEntry
from logging_utils import log


TIMING_PATTERN = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


def parse_timestamp(value: str) -> float:
    """Convert SRT timestamp string to seconds."""
    hours, minutes, seconds_ms = value.split(":")
    seconds, millis = seconds_ms.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp string."""
    if seconds < 0:
        seconds = 0
    total_millis = int(round(seconds * 1000))
    hours = total_millis // 3_600_000
    total_millis %= 3_600_000
    minutes = total_millis // 60_000
    total_millis %= 60_000
    secs = total_millis // 1000
    millis = total_millis % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_srt(text: str) -> list[SubtitleEntry]:
    """Parse SRT file content into SubtitleEntry objects."""
    log(f"\n[PARSE SRT] Parsing subtitle file...")
    entries: list[SubtitleEntry] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    log(f"[PARSE SRT] Found {len(blocks)} subtitle blocks to process")
    
    for block_num, block in enumerate(blocks, start=1):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            log(f"[PARSE SRT] Skipping block {block_num}: insufficient lines")
            continue
        try:
            index = int(lines[0])
            timing_line = lines[1]
            content_start = 2
        except ValueError:
            index = len(entries) + 1
            timing_line = lines[0]
            content_start = 1
        match = TIMING_PATTERN.search(timing_line)
        if not match:
            log(f"[PARSE SRT] Skipping block {block_num}: no valid timing pattern")
            continue
        entry = SubtitleEntry(
            index=index,
            start=parse_timestamp(match.group("start")),
            end=parse_timestamp(match.group("end")),
            text="\n".join(lines[content_start:]),
        )
        entries.append(entry)
    
    log(f"[PARSE SRT] Successfully parsed {len(entries)} subtitle entries")
    return entries


def serialize_srt(entries: list[SubtitleEntry]) -> str:
    """Convert SubtitleEntry objects to SRT file format."""
    blocks = []
    for position, entry in enumerate(entries, start=1):
        blocks.append(
            "\n".join(
                [
                    str(position),
                    f"{format_timestamp(entry.start)} --> {format_timestamp(entry.end)}",
                    entry.text,
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"
