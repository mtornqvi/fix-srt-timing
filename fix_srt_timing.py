from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
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


@dataclass
class SubtitleEntry:
    index: int
    start: float
    end: float
    text: str


def load_dotenv(path: Path) -> dict[str, str]:
    log(f"\n[LOAD ENV] Reading configuration from: {path}")
    settings: dict[str, str] = {}
    if not path.exists():
        log(f"[LOAD ENV] No .env file found, using defaults")
        return settings
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        settings[key.strip()] = value.strip().strip('"').strip("'")
    log(f"[LOAD ENV] Loaded {len(settings)} configuration settings")
    for key, value in settings.items():
        log(f"[LOAD ENV]   {key} = {value}")
    return settings


def parse_timestamp(value: str) -> float:
    hours, minutes, seconds_ms = value.split(":")
    seconds, millis = seconds_ms.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def format_timestamp(seconds: float) -> str:
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


TIMING_PATTERN = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)
SIMILARITY_THRESHOLD = 0.6
MIN_SUBTITLE_DURATION_SECONDS = 0.5


def parse_srt(text: str) -> list[SubtitleEntry]:
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


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalized_text(a), _normalized_text(b)).ratio()


def align_subtitles_to_transcript(
    entries: list[SubtitleEntry],
    transcript_segments: list[dict[str, object]],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    min_duration_seconds: float = MIN_SUBTITLE_DURATION_SECONDS,
) -> list[SubtitleEntry]:
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
        log(f"[ALIGN]   Text preview: {entry.text[:50]}..." if len(entry.text) > 50 else f"[ALIGN]   Text: {entry.text}")
        
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
            log(f"[ALIGN]   ✓ Matched with transcript (similarity: {best_score:.2f})")
            log(f"[ALIGN]   Transcript text: {str(best.get('text', ''))[:50]}...")
            log(f"[ALIGN]   New timing from transcript: {format_timestamp(start)} --> {format_timestamp(end)}")
        else:
            start = entry.start
            end = entry.end
            log(f"[ALIGN]   ✗ No good match found (best similarity: {best_score:.2f})")
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


def transcribe_video(video_file: Path, model_size: str = "base") -> list[dict[str, object]]:
    log(f"\n[TRANSCRIBE] Starting transcription process")
    log(f"[TRANSCRIBE] Video file: {video_file}")
    log(f"[TRANSCRIBE] Model size: {model_size}")
    
    # Check if transcript already exists
    transcript_file = video_file.with_suffix(".transcript.json")
    if transcript_file.exists():
        log(f"[TRANSCRIBE] Found existing transcript: {transcript_file}")
        log(f"[TRANSCRIBE] Skipping transcription to save time")
        transcript = json.loads(transcript_file.read_text(encoding="utf-8"))
        segments = transcript.get("segments", [])
        log(f"[TRANSCRIBE] Loaded {len(segments)} transcript segments from cache")
        return segments
    
    log(f"[TRANSCRIBE] No existing transcript found, creating new one...")
    log(f"[TRANSCRIBE] This may take several minutes depending on video length")
    import_failure: Exception | None = None
    whisper_failure: Exception | None = None
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        import_failure = exc
    else:
        try:
            log(f"[TRANSCRIBE] Loading Whisper model '{model_size}'...")
            model = whisper.load_model(model_size)
            log(f"[TRANSCRIBE] Model loaded successfully")
            log(f"[TRANSCRIBE] Transcribing audio (fp16=False for CPU compatibility)...")
            result = model.transcribe(str(video_file), verbose=False, fp16=False)
            segments = result.get("segments", [])
            log(f"[TRANSCRIBE] Transcription complete! Generated {len(segments)} segments")
            # Save transcript to target folder
            transcript_file.write_text(
                json.dumps({"segments": segments}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            log(f"[TRANSCRIBE] Transcript saved to: {transcript_file}")
            log(f"[TRANSCRIBE] Future runs will reuse this transcript")
            return segments
        except Exception as exc:
            whisper_failure = exc
            log(f"[TRANSCRIBE] Python whisper failed with error: {exc}")
            log(f"[TRANSCRIBE] Error type: {type(exc).__name__}")

    with tempfile.TemporaryDirectory() as temp_dir:
        cmd = [
            "whisper",
            str(video_file),
            "--model",
            model_size,
            "--output_format",
            "json",
            "--output_dir",
            temp_dir,
            "--fp16",
            "False",
            "--verbose",
            "False",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            whisper_reason = f"whisper python failure: {whisper_failure}; " if whisper_failure else ""
            import_reason = f"import failure: {import_failure}; " if import_failure else ""
            raise RuntimeError(
                "Unable to transcribe video. Install openai-whisper (pip install openai-whisper) "
                "or make sure the whisper CLI is available. "
                f"{import_reason}{whisper_reason}cli failure: {exc}"
            ) from exc

        temp_transcript = Path(temp_dir) / f"{video_file.stem}.json"
        if not temp_transcript.exists():
            raise RuntimeError("Whisper CLI did not produce a transcript JSON file.")
        transcript = json.loads(temp_transcript.read_text(encoding="utf-8"))
        # Save transcript to target folder
        transcript_file.write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        log(f"[TRANSCRIBE] Transcript saved to: {transcript_file}")
        log(f"[TRANSCRIBE] Future runs will reuse this transcript")
        return transcript.get("segments", [])


def resolve_paths(settings: dict[str, str], repository_root: Path) -> tuple[Path, Path]:
    log(f"\n[RESOLVE] Resolving file paths...")
    folder = settings.get("PROCESS_FOLDER", ".")
    process_dir = (repository_root / folder).resolve()
    log(f"[RESOLVE] Target folder: {process_dir}")
    
    stem = settings.get("PROCESS_FILE")
    video_name = settings.get("VIDEO_FILE")
    subtitle_name = settings.get("SUBTITLE_FILE")
    
    if stem:
        log(f"[RESOLVE] Using PROCESS_FILE: {stem}")
        video_name = video_name or f"{stem}.mp4"
        subtitle_name = subtitle_name or f"{stem}.srt"
    else:
        log(f"[RESOLVE] Using explicit VIDEO_FILE and SUBTITLE_FILE")
    
    if not video_name or not subtitle_name:
        raise ValueError("Set PROCESS_FILE or both VIDEO_FILE and SUBTITLE_FILE in .env")

    video_path = (process_dir / video_name).resolve()
    subtitle_path = (process_dir / subtitle_name).resolve()
    
    log(f"[RESOLVE] Video file: {video_path}")
    log(f"[RESOLVE] Subtitle file: {subtitle_path}")
    
    if video_path.suffix.lower() != ".mp4":
        raise ValueError(f"Expected .mp4 video file, got: {video_path.name}")
    if subtitle_path.suffix.lower() != ".srt":
        raise ValueError(f"Expected .srt subtitle file, got: {subtitle_path.name}")
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not subtitle_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    
    log(f"[RESOLVE] ✓ All files exist and are valid")
    return video_path, subtitle_path


def backup_subtitle_file(subtitle_path: Path) -> Path:
    """Create a timestamped backup of the subtitle file."""
    log(f"\n[BACKUP] Creating backup of original subtitle file...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = subtitle_path.with_suffix(f".backup.{timestamp}.srt")
    shutil.copy2(subtitle_path, backup_path)
    log(f"[BACKUP] Backup created: {backup_path}")
    log(f"[BACKUP] Original file is safe and can be restored if needed")
    return backup_path


def process_from_env(env_path: Path = Path(".env")) -> tuple[Path, Path]:
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
        if _log_file:
            log(f"\n[ERROR] Process failed: {exc}")
            import traceback
            log(traceback.format_exc())
        # Re-raise for console
        raise
    finally:
        close_logging()
