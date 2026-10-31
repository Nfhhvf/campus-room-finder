"""Prepare the initial timetable cache. Re-running safely checks for updates."""
if __name__ == '__main__':
    import sys
    from app_updates import before_launch
    before_launch(__file__, sys.argv)

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path

from timetable_cache import refresh
from terminal_ui import Progress, heading, display_day
from terminal_ui import QuitSearch
import preferences

ROOT = Path(__file__).resolve().parent


def install_command(root=ROOT, *, home=None, shell=None):
    """Install a per-user launcher and append one PATH entry when necessary."""
    if os.name == 'nt':
        print('On Windows, start with: python rooms.py')
        return None
    home = Path.home() if home is None else Path(home)
    directory = home / '.local' / 'bin'
    launcher = directory / 'roomfinder'
    marker = '# campus-room-finder launcher'
    if launcher.is_symlink() or (launcher.exists() and marker not in launcher.read_text()):
        raise ValueError(f'{launcher} already belongs to another command; it was not changed.')
    directory.mkdir(parents=True, exist_ok=True)
    script = (Path(root) / 'rooms.py').resolve()
    contents = f'#!/bin/sh\n{marker}\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "$@"\n'
    # Use a replace rather than editing a launcher while another shell reads it.
    import tempfile
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(contents)
        temporary.chmod(0o755)
        temporary.replace(launcher)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    shell = Path(shell or os.environ.get('SHELL', '')).name
    profile = None
    if str(directory) not in os.environ.get('PATH', '').split(os.pathsep):
        if shell == 'zsh':
            profile = Path(os.environ.get('ZDOTDIR') or home) / '.zshrc'
        elif shell == 'bash':
            profile = home / ('.bash_profile' if sys.platform == 'darwin' else '.bashrc')
        if profile is not None:
            line = f'export PATH={shlex.quote(str(directory))}:"$PATH"'
            old = profile.read_text() if profile.exists() else ''
            if line not in old.splitlines():
                profile.parent.mkdir(parents=True, exist_ok=True)
                with profile.open('a') as handle:
                    handle.write('\n# Campus Room Finder\n' + line + '\n')
    print(f'Command installed: {launcher}')
    if profile is not None:
        print(f'Open a new terminal, or run: source {shlex.quote(str(profile))}')
    elif str(directory) not in os.environ.get('PATH', '').split(os.pathsep):
        print(f'Add {directory} to your shell PATH to use roomfinder from any folder.')
    print('Start: roomfinder')
    return launcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'settings.json'))
    parser.add_argument('--cache', default=str(ROOT / '.cache/timetables.json'))
    parser.add_argument('--no-update', action='store_true', help='Skip the GitHub code check')
    parser.add_argument('--command-only', action='store_true', help='Install roomfinder without downloading timetables again')
    args = parser.parse_args()
    started = time.monotonic()
    try:
        heading('Command setup' if args.command_only else 'First-time setup')
        if args.command_only:
            install_command()
            return 0
        prefs = preferences.load()
        if sys.stdin.isatty() and not preferences.location().exists():
            prefs = preferences.first_setup(prefs)
        preferences.apply_display(prefs)
        print('Downloads the timetables once, then checks for updates on later runs.\n', flush=True)
        config = json.loads(Path(args.config).read_text())
        with Progress('Timetable setup') as progress:
            schedule, status = refresh(config, args.cache, progress=progress.update)
        # Validate declared coverage and imported lesson structure before calling
        # setup ready. Import here so its timezone prerequisite is checked too.
        from datetime import date
        from rooms import validate_schedule
        validate_schedule(schedule, date.fromisoformat(schedule['coverage']['from']))
        print(f"Ready: {len(schedule['rooms'])} rooms, {len(schedule['lessons'])} booking records.")
        print(f"Supported dates: {display_day(schedule['coverage']['from'])} to {display_day(schedule['coverage']['to'])}")
        print(f"Checked {status['checked']} source files in {time.monotonic() - started:.1f}s.")
        launcher = install_command()
        command = 'roomfinder' if launcher else 'python rooms.py'
        print(f'Without internet: {command} --offline (saved data, not checked for changes)')
        return 0
    except (QuitSearch, KeyboardInterrupt, EOFError):
        print('\nClosed.')
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Setup could not complete: {exc}')
        print('Check the connection/source error and run this setup command again.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
