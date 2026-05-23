"""Configuration management and constants."""

from __future__ import annotations

from pathlib import Path

from logging_utils import log


# Default configuration values
SIMILARITY_THRESHOLD = 0.6
MIN_SUBTITLE_DURATION_SECONDS = 0.5


def load_dotenv(path: Path) -> dict[str, str]:
    """Load environment variables from a .env file."""
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


def resolve_paths(settings: dict[str, str], repository_root: Path) -> tuple[Path, Path]:
    """Resolve video and subtitle file paths from configuration."""
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
