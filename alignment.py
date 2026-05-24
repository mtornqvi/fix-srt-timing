"""Subtitle alignment with transcript using text similarity."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from models import SubtitleEntry
from srt_parser import format_timestamp
from logging_utils import log
from config import SIMILARITY_THRESHOLD, MIN_SUBTITLE_DURATION_SECONDS


def _normalized_text(value: str) -> str:
    """Normalize text for similarity comparison."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


def _similarity(a: str, b: str) -> float:
    """Calculate text similarity ratio between two strings."""
    return SequenceMatcher(None, _normalized_text(a), _normalized_text(b)).ratio()


def align_subtitles_to_transcript(
    entries: list[SubtitleEntry],
    transcript_segments: list[dict[str, object]],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    min_duration_seconds: float = MIN_SUBTITLE_DURATION_SECONDS,
) -> list[SubtitleEntry]:
    """Align subtitle timings with transcript segments using text similarity matching."""
    log(f"\n[ALIGN] Starting alignment process")
    log(f"[ALIGN] Subtitle entries: {len(entries)}")
    log(f"[ALIGN] Transcript segments: {len(transcript_segments)}")
    log(f"[ALIGN] Similarity threshold: {similarity_threshold}")
    log(f"[ALIGN] Minimum duration: {min_duration_seconds}s")
    
    aligned: list[SubtitleEntry] = []
    previous_end = 0.0
    matched_count = 0
    
    for idx, entry in enumerate(entries, start=1):
        log(f"\n[ALIGN] Processing subtitle {idx}/{len(entries)}")
        log(f"[ALIGN]   Original timing: {format_timestamp(entry.start)} --> {format_timestamp(entry.end)}")
        log(f"[ALIGN]   Subtitle text: {entry.text}")
        
        best = None
        best_score = 0.0
        for segment in transcript_segments:
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            score = _similarity(entry.text, text)
            if score > best_score:
                best_score = score
                best = segment

        if best and best_score > similarity_threshold:
            start = float(best.get("start", entry.start))
            end = float(best.get("end", entry.end))
            matched_count += 1
            transcript_text = str(best.get('text', '')).strip()
            log(f"[ALIGN]   ✓ Matched with transcript (similarity: {best_score:.2f})")
            log(f"[ALIGN]   Transcript text: {transcript_text}")
            log(f"[ALIGN]   New timing from transcript: {format_timestamp(start)} --> {format_timestamp(end)}")
        else:
            start = entry.start
            end = entry.end
            best_transcript_text = str(best.get('text', '')).strip() if best else "(no match)"
            log(f"[ALIGN]   ✗ No good match found (best similarity: {best_score:.2f})")
            log(f"[ALIGN]   Best transcript candidate: {best_transcript_text}")
            log(f"[ALIGN]   Keeping original timing")

        # Ensure non-overlapping and minimum duration
        original_start = start
        start = max(start, previous_end)
        if start != original_start:
            log(f"[ALIGN]   Adjusted start time to avoid overlap: {format_timestamp(original_start)} -> {format_timestamp(start)}")
        
        original_end = end
        end = max(end, start + min_duration_seconds)
        if end != original_end:
            log(f"[ALIGN]   Adjusted end time for minimum duration: {format_timestamp(original_end)} -> {format_timestamp(end)}")
        
        previous_end = end
        log(f"[ALIGN]   Final timing: {format_timestamp(start)} --> {format_timestamp(end)}")
        
        aligned.append(SubtitleEntry(index=entry.index, start=start, end=end, text=entry.text))
    
    log(f"\n[ALIGN] Alignment complete!")
    log(f"[ALIGN] Matched {matched_count}/{len(entries)} subtitles with transcript ({matched_count/len(entries)*100:.1f}%)")
    return aligned
