"""Prepare the initial timetable cache. Re-running safely checks for updates."""
import argparse
import json
import time
from pathlib import Path

from timetable_cache import refresh

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'settings.json'))
    parser.add_argument('--cache', default=str(ROOT / '.cache/timetables.json'))
    args = parser.parse_args()
    started = time.monotonic()
    try:
        print('Campus Est · first-time timetable setup', flush=True)
        print('Downloading on first setup; checking updates if saved data already exists.', flush=True)
        config = json.loads(Path(args.config).read_text())
        schedule, status = refresh(config, args.cache, progress=lambda text: print(text, flush=True))
        # Validate declared coverage and imported lesson structure before calling
        # setup ready. Import here so its timezone prerequisite is checked too.
        from datetime import date
        from rooms import validate_schedule
        validate_schedule(schedule, date.fromisoformat(schedule['coverage']['from']))
        print(f"Ready: {len(schedule['rooms'])} rooms, {len(schedule['lessons'])} booking records.")
        print(f"Supported dates: {schedule['coverage']['from']} to {schedule['coverage']['to']}")
        print(f"Checked {status['checked']} source files in {time.monotonic() - started:.1f}s.")
        print('Start a search: python3 rooms.py')
        print('Without internet: python3 rooms.py --offline (saved data, not checked for changes)')
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Setup could not complete: {exc}')
        print('Check the connection/source error and run this setup command again.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
