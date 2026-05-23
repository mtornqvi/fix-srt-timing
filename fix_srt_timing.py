"""Main script for fixing subtitle timing using audio transcription."""

from __future__ import annotations

import traceback
from pathlib import Path

from alignment import align_subtitles_to_transcript
from config import (
    SIMILARITY_THRESHOLD,
    MIN_SUBTITLE_DURATION_SECONDS,
    load_dotenv,
    resolve_paths,
)
from logging_utils import log, setup_logging, close_logging, get_log_file
from srt_parser import parse_srt, serialize_srt
from transcription import transcribe_video
from utils import backup_subtitle_file


def process_from_env(env_path: Path = Path(".env")) -> tuple[Path, Path]:
    """Main processing function that orchestrates the subtitle timing fix."""
    repository_root = env_path.resolve().parent
    
    # Load settings first to resolve video path
    settings = load_dotenv(env_path)
    video_path, subtitle_path = resolve_paths(settings, repository_root=repository_root)
    
    # Setup logging with video file name
    log_path = setup_logging(video_path)
    
    log("="*80)
    log("SUBTITLE TIMING FIX - STARTING PROCESS")
    log("="*80)
    log(f"Log file: {log_path}")
    
    log(f"\n[CONFIG] Processing configuration parameters...")
    model_size = settings.get("WHISPER_MODEL", "base")
    log(f"[CONFIG] Whisper model: {model_size}")
    
    try:
        similarity_threshold = float(
            settings.get("ALIGNMENT_SIMILARITY_THRESHOLD", SIMILARITY_THRESHOLD)
        )
        log(f"[CONFIG] Similarity threshold: {similarity_threshold}")
    except ValueError as exc:
        raise ValueError("ALIGNMENT_SIMILARITY_THRESHOLD must be a valid float value.") from exc
    
    try:
        min_duration_seconds = float(
            settings.get("MIN_SUBTITLE_DURATION_SECONDS", MIN_SUBTITLE_DURATION_SECONDS)
        )
        log(f"[CONFIG] Minimum subtitle duration: {min_duration_seconds}s")
    except ValueError as exc:
        raise ValueError("MIN_SUBTITLE_DURATION_SECONDS must be a valid float value.") from exc
    
    # Step 1: Transcribe video
    transcript_segments = transcribe_video(video_path, model_size=model_size)
    
    # Step 2: Parse existing subtitles
    entries = parse_srt(subtitle_path.read_text(encoding="utf-8"))
    
    # Step 3: Align subtitles with transcript
    adjusted = align_subtitles_to_transcript(
        entries,
        transcript_segments,
        similarity_threshold=similarity_threshold,
        min_duration_seconds=min_duration_seconds,
    )
    
    # Step 4: Backup original file
    backup_path = backup_subtitle_file(subtitle_path)
    
    # Step 5: Write updated subtitles
    log(f"\n[SAVE] Writing updated subtitles to: {subtitle_path}")
    subtitle_path.write_text(serialize_srt(adjusted), encoding="utf-8")
    log(f"[SAVE] ✓ Subtitle file updated successfully")
    
    return subtitle_path, log_path


if __name__ == "__main__":
    try:
        updated_file, log_path = process_from_env()
        log("\n" + "="*80)
        log(f"✓ SUCCESS! Updated subtitle timings in: {updated_file}")
        log(f"Log saved to: {log_path}")
        log("="*80)
        
        # Print only the essential info to console
        print(f"✓ Subtitle file updated: {updated_file}")
        print(f"Log file: {log_path}")
    except Exception as exc:
        # Log the error
        if get_log_file():
            log(f"\n[ERROR] Process failed: {exc}")
            log(traceback.format_exc())
        # Re-raise for console
        raise
    finally:
        close_logging()

