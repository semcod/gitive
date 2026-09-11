"""Safe data retention and cleanup for historical runs and telemetry."""
import os
from pathlib import Path
import re
import shutil
import time

RUN_DIR_RE = re.compile(r'^\d{8}T\d{6}Z-[0-9a-zA-Z_-]{4,}$')


def dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += dir_size(Path(entry.path))
            except (OSError, ValueError):
                continue
    except (OSError, ValueError):
        pass
    return total


def clean_data(data_path, active_run=None, days=3, keep_last=5, dry_run=False):
    """Prune historical run directories while protecting active runs and the newest N runs."""
    data = Path(data_path).resolve()
    if not data.is_dir():
        raise ValueError('Katalog danych nie istnieje')

    now = time.time()
    cutoff = now - (max(0, days) * 86400) if days > 0 else now + 1

    all_runs = []
    for item in sorted(data.iterdir()):
        if item.is_dir() and RUN_DIR_RE.match(item.name):
            try:
                mtime = item.stat().st_mtime
            except OSError:
                mtime = 0
            all_runs.append((item, mtime))

    all_runs.sort(key=lambda x: (x[1], x[0].name), reverse=True)

    kept = []
    candidates = []
    for i, (folder, mtime) in enumerate(all_runs):
        if folder.name == active_run:
            kept.append(folder.name)
            continue
        if i < keep_last:
            kept.append(folder.name)
            continue
        if days == 0 or mtime < cutoff:
            candidates.append(folder)
        else:
            kept.append(folder.name)

    freed_bytes = 0
    cleaned_runs = []
    for folder in candidates:
        size = dir_size(folder)
        freed_bytes += size
        cleaned_runs.append(folder.name)
        if not dry_run:
            shutil.rmtree(folder, ignore_errors=True)

    web_check_cutoff = now - 86400
    for item in data.glob('web-check-*'):
        if item.is_dir():
            try:
                if item.stat().st_mtime < web_check_cutoff:
                    freed_bytes += dir_size(item)
                    if not dry_run:
                        shutil.rmtree(item, ignore_errors=True)
            except OSError:
                pass

    return {
        'ok': True,
        'dry_run': dry_run,
        'days': days,
        'keep_last': keep_last,
        'freed_bytes': freed_bytes,
        'cleaned_runs': cleaned_runs,
        'cleaned_count': len(cleaned_runs),
        'kept_runs': kept,
        'kept_count': len(kept),
        'total_runs': len(all_runs),
    }
