"""Maintain a dated launcher for the private noVNC Chromium session.

Only session-file modification times are inspected; profile contents are not read.
This script runs inside the desktop, never against the PC profile.
"""
import argparse
import fcntl
from datetime import datetime
from pathlib import Path
import time
from zoneinfo import ZoneInfo


def update():
    home = Path.home()
    profile = home / '.config/chromium/Default'
    files = [p for pattern in ('Sessions/Session_*', 'Sessions/Tabs_*')
             for p in profile.glob(pattern) if p.is_file() and not p.is_symlink()]
    times = []
    for path in files:
        try:
            times.append(path.stat().st_mtime)
        except FileNotFoundError:
            pass  # Chromium can rotate session files during inspection.
    date = (datetime.fromtimestamp(max(times), ZoneInfo('Europe/Warsaw')).strftime('%Y-%m-%d %H:%M:%S')
            if times else 'brak zapisu sesji')
    desktop = home / 'Desktop'
    desktop.mkdir(exist_ok=True)
    target = desktop / 'gitive-chromium-session.desktop'
    content = ('[Desktop Entry]\nType=Application\n'
               f'Name=Chromium noVNC — {date}\n'
               'Comment=Ostatni zapis plików sesji (Europe/Warsaw). Prywatny profil noVNC; nie import Chrome z PC.\n'
               'Exec=chromium --user-data-dir=/home/browser/.config/chromium --password-store=basic --restore-last-session --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222\n'
               'Icon=chromium\nTerminal=false\nStartupNotify=true\n')
    if not target.exists() or target.read_text() != content:
        temporary = target.with_suffix('.tmp')
        temporary.write_text(content)
        temporary.chmod(0o755)
        temporary.replace(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if args.watch:
        lock = (Path.home() / ".local/bin/gitive-session-date.lock").open("w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(0)
    while True:
        update()
        if not args.watch:
            break
        time.sleep(60)
