"""Utility functions for subtitle processing."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from logging_utils import log


def backup_subtitle_file(subtitle_path: Path) -> Path:
    """Create a timestamped backup of the subtitle file."""
    log(f"\n[BACKUP] Creating backup of original subtitle file...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = subtitle_path.with_suffix(f".backup.{timestamp}.srt")
    shutil.copy2(subtitle_path, backup_path)
    log(f"[BACKUP] Backup created: {backup_path}")
    log(f"[BACKUP] Original file is safe and can be restored if needed")
    return backup_path
