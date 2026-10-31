"""Terminal classroom availability search. Python 3.11+, no dependencies."""
import argparse
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
from timetable_cache import refresh

ZONE = ZoneInfo('Europe/Zurich')
CUTOFF = time(17, 30)
ROOT = Path(__file__).resolve().parent


def clock(value):
    return time.fromisoformat(value)


def load_schedule(path, day):
    data = json.loads(Path(path).read_text())
    return validate_schedule(data, day)


def validate_schedule(data, day):
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported schedule format.')
    if not data.get('sources'):
        raise ValueError('Schedule must identify its timetable sources.')
    coverage = data['coverage']
    if not date.fromisoformat(coverage['from']) <= day <= date.fromisoformat(coverage['to']):
        raise ValueError('This date is outside the timetable coverage. Refresh the data.')
    if not coverage.get('supsi_all_years') or not coverage.get('usi_at_supsi'):
        raise ValueError('Incomplete coverage: all SUPSI years and USI lessons at SUPSI must be checked.')
    rooms = data['rooms']
    ids = [r['id'] for r in rooms]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate room identifiers.')
    for event in data['lessons']:
        date.fromisoformat(event['date'])
        if event['room'] not in ids:
            raise ValueError('Lesson references an unknown room.')
        if clock(event['start']) >= clock(event['end']):
            raise ValueError('Lesson end must follow its start on the same day.')
    return data


def free_slots(lessons, start, end):
    """Subtract occupied half-open intervals, merging overlaps and adjacency."""
    cursor = start
    for lesson in sorted(lessons, key=lambda e: clock(e['start'])):
        left, right = clock(lesson['start']), clock(lesson['end'])
        if right <= cursor or left >= end:
            continue
        if left > cursor:
            yield cursor, left
        cursor = max(cursor, right)
        if cursor >= end:
            return
    if cursor < end:
        yield cursor, end


def search(data, day, mode, start, end):
    results = []
    for room in sorted(data['rooms'], key=lambda r: r['id']):
        if (room['campus'], room['floor'], room['sector']) not in {
            ('Campus Est', 1, 'A'), ('Campus Est', 1, 'B')
        } or room.get('is_classroom', room.get('student_use_allowed')) is not True:
            continue
        lessons = [e for e in data['lessons'] if e['room'] == room['id'] and e['date'] == day.isoformat()]
        slots = list(free_slots(lessons, start, end))
        if mode == 'evening':
            slots = [(a, b) for a, b in slots if a == start and b == end and start < CUTOFF]
        elif mode == 'now':
            slots = [(a, b) for a, b in slots if a == start]
        for a, b in slots:
            results.append((room['id'], a, b, a < CUTOFF))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', help='Read a manually prepared schedule without online checks')
    parser.add_argument('--config', default=str(ROOT / 'settings.json'), help='Online timetable source configuration')
    parser.add_argument('--cache', default=str(ROOT / '.cache/timetables.json'))
    parser.add_argument('--offline', action='store_true', help='Explicitly use saved lessons without checking updates')
    parser.add_argument('--demo', action='store_true', help='Use fictional demonstration data')
    parser.add_argument('--mode', choices=['evening', 'now', 'day'])
    parser.add_argument('--date', dest='day')
    parser.add_argument('--start')
    parser.add_argument('--end')
    args = parser.parse_args()
    try:
        print('Campus Est · floor 1 · sectors A and B · Europe/Zurich')
        if args.demo:
            print('DEMO: fictional rooms and lessons. Do not use these results to choose a room.')
        if args.demo and (args.data or args.offline):
            raise ValueError('--demo cannot be combined with --data or --offline.')
        if args.data and args.offline:
            raise ValueError('--offline applies to the online cache; use --data by itself for a local file.')
        online_data = None
        if not args.demo and not args.data:
            if not Path(args.config).exists():
                raise ValueError(f'Configuration file not found: {args.config}')
            config = json.loads(Path(args.config).read_text())
            print('Using saved lessons (OFFLINE).' if args.offline else 'Discovering and checking SUPSI + USI timetables…', flush=True)
            online_data, status = refresh(config, args.cache, offline=args.offline,
                                          progress=lambda message: print(message, flush=True))
            checked_at = datetime.fromisoformat(status['checked_at']).astimezone(ZONE).strftime('%Y-%m-%d %H:%M:%S %Z')
            if status['offline']:
                print(f"OFFLINE — changes have NOT been checked. Last successful check: {checked_at}")
            else:
                changed = 'updated' if status['bookings_changed'] else 'unchanged'
                print(f"Checked {status['checked']} sources; {len(status['changed'])} files refreshed; "
                      f"lesson list {changed}. Last checked: {checked_at}")
            summary = online_data.get('summary', {})
            if summary:
                print(f"{summary['rooms']} rooms · {summary['usi_programmes']} USI programmes / "
                      f"{summary['usi_calendars']} calendars · {summary['supsi_rooms']} SUPSI room timetables")
                print(f"SUPSI published update: {summary['supsi_published_update']}")
            print(f"Supported dates: {online_data['coverage']['from']} to {online_data['coverage']['to']}")
        mode = args.mode
        if mode is None:
            print('1. Free through my study session\n2. Free at arrival, until next lesson\n3. All free slots in a day')
            choice = input('Search mode [1]: ').strip() or '1'
            if choice not in {'1', '2', '3'}:
                raise ValueError('Choose 1, 2 or 3.')
            mode = {'1': 'evening', '2': 'now', '3': 'day'}[choice]
        today = datetime.now(ZONE).date().isoformat()
        day = date.fromisoformat(args.day or input(f'Date [{today}]: ').strip() or today)
        start = clock(args.start or input('Arrival / search starts [16:30]: ').strip() or '16:30')
        end = clock(args.end or input('Study until / search ends [22:00]: ').strip() or '22:00')
        if start >= end:
            raise ValueError('End time must be later than start time on the same day.')
        if online_data is not None:
            data = validate_schedule(online_data, day)
        else:
            path = Path(__file__).parent / 'examples/demo.json' if args.demo else args.data
            data = load_schedule(path, day)
            if args.data:
                print('LOCAL FILE — timetable changes have NOT been checked.')
        print(f"Imported {len(data['lessons'])} room bookings from {len(data['sources'])} timetables.")
        for note in data.get('notes', []):
            print(note)
        print('Timetable gaps only; unlisted bookings and actual access are not verified.')
        if start >= CUTOFF:
            print('Arrival is at/after 17:30: badge entry is unavailable under your stated rule.')
        results = search(data, day, mode, start, end)
        for room, a, b, enter in results:
            access = 'entry before cutoff' if enter else 'entry unavailable after cutoff'
            print(f'{room:16} {a:%H:%M}–{b:%H:%M}  {access}')
        if not results:
            print('No matching timetable gaps found for this search.')
        return 0
    except (ValueError, KeyError, TypeError, OSError, EOFError) as exc:
        print(f'Cannot search: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
