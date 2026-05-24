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


def _check_multi_segment_match(
    subtitle_text: str,
    transcript_segments: list[dict[str, object]],
    start_idx: int,
    max_lookahead: int = 3,
) -> tuple[int, float]:
    """Check if subtitle spans multiple consecutive transcript segments.
    
    Returns:
        (end_segment_idx, combined_similarity) - Index of last matching segment and combined similarity
    """
    combined_text = str(transcript_segments[start_idx].get("text", "")).strip()
    best_end_idx = start_idx
    best_similarity = _similarity(subtitle_text, combined_text)
    
    # Try combining with subsequent segments
    for offset in range(1, min(max_lookahead, len(transcript_segments) - start_idx)):
        next_idx = start_idx + offset
        next_text = str(transcript_segments[next_idx].get("text", "")).strip()
        combined_text += " " + next_text
        
        combined_similarity = _similarity(subtitle_text, combined_text)
        
        # If combining improves similarity, extend the match
        if combined_similarity > best_similarity:
            best_similarity = combined_similarity
            best_end_idx = next_idx
        else:
            # Stop if similarity stops improving
            break
    
    return best_end_idx, best_similarity


def align_subtitles_to_transcript(
    entries: list[SubtitleEntry],
    transcript_segments: list[dict[str, object]],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    min_duration_seconds: float = MIN_SUBTITLE_DURATION_SECONDS,
) -> list[SubtitleEntry]:
    """Align subtitle timings with transcript segments using sequential text similarity matching.
    
    This algorithm processes subtitles in order and maintains a cursor in the transcript
    to ensure temporal consistency and prevent segment reuse.
    """
    log(f"\n[ALIGN] Starting sequential alignment process")
    log(f"[ALIGN] Subtitle entries: {len(entries)}")
    log(f"[ALIGN] Transcript segments: {len(transcript_segments)}")
    log(f"[ALIGN] Similarity threshold: {similarity_threshold}")
    log(f"[ALIGN] Minimum duration: {min_duration_seconds}s")
    log(f"[ALIGN] Using sequential matching to maintain temporal order")
    
    aligned: list[SubtitleEntry] = []
    previous_end = 0.0
    matched_count = 0
    transcript_cursor = 0  # Track position in transcript to enforce sequential matching
    
    for idx, entry in enumerate(entries, start=1):
        log(f"\n[ALIGN] Processing subtitle {idx}/{len(entries)}")
        log(f"[ALIGN]   Original timing: {format_timestamp(entry.start)} --> {format_timestamp(entry.end)}")
        log(f"[ALIGN]   Subtitle text: {entry.text}")
        
        best = None
        best_score = 0.0
        best_segment_idx = transcript_cursor
        best_weighted_score = 0.0
        
        # Search forward from cursor position (with small lookback window for flexibility)
        search_start = max(0, transcript_cursor - 5)  # Allow looking back 5 segments
        log(f"[ALIGN]   Searching transcript from segment {search_start} to {len(transcript_segments)}")
        
        # Expected time for this subtitle (from previous end)
        expected_start_time = previous_end
        
        for seg_idx in range(search_start, len(transcript_segments)):
            segment = transcript_segments[seg_idx]
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            
            similarity_score = _similarity(entry.text, text)
            
            # Calculate temporal proximity bonus
            # Penalize matches that are far from the expected time
            segment_start = float(segment.get("start", 0))
            time_distance = abs(segment_start - expected_start_time)
            
            # Temporal penalty: reduce score if match is >10 seconds away from expected time
            # For every 10 seconds of distance, reduce the effective score by 0.1
            temporal_penalty = min(0.3, time_distance / 100.0)  # Cap penalty at 0.3
            
            weighted_score = similarity_score - temporal_penalty
            
            if weighted_score > best_weighted_score:
                best_weighted_score = weighted_score
                best_score = similarity_score  # Keep original similarity for logging
                best = segment
                best_segment_idx = seg_idx

        # Check for multi-segment match if we found any candidate
        # (even if below threshold - combining might improve it)
        multi_end_idx = best_segment_idx
        multi_similarity = best_score
        
        if best is not None:
            multi_end_idx, multi_similarity = _check_multi_segment_match(
                entry.text, transcript_segments, best_segment_idx, max_lookahead=3
            )
            
            # Recalculate weighted score for multi-segment match
            if multi_end_idx > best_segment_idx:
                multi_start_time = float(best.get("start", 0))
                multi_time_distance = abs(multi_start_time - expected_start_time)
                multi_temporal_penalty = min(0.3, multi_time_distance / 100.0)
                multi_weighted_score = multi_similarity - multi_temporal_penalty
            else:
                multi_weighted_score = best_weighted_score

        # Use the match if it exceeds threshold (either single or multi-segment)
        if best and max(best_weighted_score, multi_weighted_score) > similarity_threshold:
            
            start = float(best.get("start", entry.start))
            transcript_text = str(best.get('text', '')).strip()
            
            # Prefer multi-segment if it significantly improves match OR brings it above threshold
            use_multi_segment = (
                multi_end_idx > best_segment_idx and 
                (multi_similarity > best_score + 0.05 or 
                 (multi_weighted_score > similarity_threshold >= best_weighted_score))
            )
            
            if use_multi_segment:
                # Subtitle spans multiple segments - extend timing to cover all
                end_segment = transcript_segments[multi_end_idx]
                end = float(end_segment.get("end", entry.end))
                matched_count += 1
                
                # Build combined transcript text for logging
                combined_texts = []
                for seg_idx in range(best_segment_idx, multi_end_idx + 1):
                    combined_texts.append(str(transcript_segments[seg_idx].get('text', '')).strip())
                combined_transcript_text = " ".join(combined_texts)
                
                # Update cursor to skip all used segments
                transcript_cursor = multi_end_idx + 1
                
                time_jump = abs(start - expected_start_time)
                segment_count = multi_end_idx - best_segment_idx + 1
                log(f"[ALIGN]   ✓ Matched with transcript segments {best_segment_idx}-{multi_end_idx} ({segment_count} segments combined)")
                log(f"[ALIGN]   Single-segment similarity: {best_score:.2f} (weighted: {best_weighted_score:.2f})")
                log(f"[ALIGN]   Multi-segment similarity: {multi_similarity:.2f} (weighted: {multi_weighted_score:.2f})")
                if time_jump > 5.0:
                    log(f"[ALIGN]   ⚠ Large time jump: expected ~{format_timestamp(expected_start_time)}, got {format_timestamp(start)} ({time_jump:.1f}s difference)")
                log(f"[ALIGN]   Combined transcript text: {combined_transcript_text}")
                log(f"[ALIGN]   New timing from transcript: {format_timestamp(start)} --> {format_timestamp(end)}")
                log(f"[ALIGN]   Transcript cursor advanced to segment {transcript_cursor}")
            else:
                # Single segment match
                end = float(best.get("end", entry.end))
                matched_count += 1
                
                # Update cursor to prevent reusing this segment
                transcript_cursor = best_segment_idx + 1
                
                time_jump = abs(start - expected_start_time)
                log(f"[ALIGN]   ✓ Matched with transcript segment {best_segment_idx} (similarity: {best_score:.2f}, weighted: {best_weighted_score:.2f})")
                if time_jump > 5.0:
                    log(f"[ALIGN]   ⚠ Large time jump: expected ~{format_timestamp(expected_start_time)}, got {format_timestamp(start)} ({time_jump:.1f}s difference)")
                log(f"[ALIGN]   Transcript text: {transcript_text}")
                log(f"[ALIGN]   New timing from transcript: {format_timestamp(start)} --> {format_timestamp(end)}")
                log(f"[ALIGN]   Transcript cursor advanced to segment {transcript_cursor}")
        else:
            start = entry.start
            end = entry.end
            best_transcript_text = str(best.get('text', '')).strip() if best else "(no match)"
            log(f"[ALIGN]   ✗ No good match found (best similarity: {best_score:.2f}, weighted: {best_weighted_score:.2f})")
            log(f"[ALIGN]   Best transcript candidate: {best_transcript_text}")
            log(f"[ALIGN]   Keeping original timing")
            log(f"[ALIGN]   Transcript cursor remains at segment {transcript_cursor}")

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
