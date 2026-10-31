"""Terminal classroom availability search. Python 3.11+, no dependencies."""
if __name__ == '__main__':
    import sys
    from app_updates import before_launch
    before_launch(__file__, sys.argv)

import argparse
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
from timetable_cache import refresh
from terminal_ui import (Progress, QuitSearch, ask, choose_mode, choose_time,
                         color, heading, show_results, choose_query_day, parse_day, display_day, show_plans)

from study_planner import minutes, move_budget, opening_soon, plan_session

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
    parser.add_argument('--no-update', action='store_true', help='Skip the GitHub code check; still refresh timetables')
    parser.add_argument('--mode', choices=['evening', 'now', 'day'])
    parser.add_argument('--date', dest='day', help='Study date as DD-MM-YY')
    parser.add_argument('--max-moves', type=int, choices=range(5), help='Override room-change limit (0-4)')
    parser.add_argument('--move-minutes', type=int, choices=range(16), default=2, help='Minutes per room change (default: 2)')
    parser.add_argument('--start')
    parser.add_argument('--end')
    args = parser.parse_args()
    try:
        heading()
        if args.demo and (args.data or args.offline):
            raise ValueError('--demo cannot be combined with --data or --offline.')
        if args.data and args.offline:
            raise ValueError('--offline applies to saved online data; use --data by itself for a local file.')
        if args.demo or args.data:
            path = ROOT / 'examples/demo.json' if args.demo else Path(args.data)
            data = json.loads(path.read_text())
            print(color('DEMO / Fictional rooms and lessons.' if args.demo else
                        'LOCAL FILE / Changes have not been checked.', '33'))
        else:
            config = json.loads(Path(args.config).read_text())
            if args.offline:
                data, status = refresh(config, args.cache, offline=True)
            else:
                with Progress('Timetable check') as progress:
                    data, status = refresh(config, args.cache, progress=progress.update)
            checked = datetime.fromisoformat(status['checked_at']).astimezone(ZONE).strftime('%d-%m-%y %H:%M %Z')
            if status['offline']:
                print(color(f'OFFLINE / Saved data from {checked}. Changes have not been checked.', '33'))
            else:
                changed = 'Lessons updated' if status['bookings_changed'] else 'No lesson changes'
                print(color(f'{changed} / Checked {checked}', '32'))
        coverage = data['coverage']
        validate_schedule(data, date.fromisoformat(coverage['from']))
        summary = data.get('summary', {})
        if summary:
            print(f"{summary['rooms']} rooms / SUPSI + {summary['usi_programmes']} USI programmes")
        print(f"Dates: {display_day(coverage['from'])} to {display_day(coverage['to'])}")
        if data.get('notes'):
            print('SUPSI uses a weekly pattern; dated exceptions may be missing.')
        print('Published lesson gaps only. Room access and unlisted bookings are not verified.\n')
        repeat = sys.stdin.isatty() and not any((args.mode, args.day, args.start, args.end))
        while True:
            mode = args.mode or choose_mode()
            now = datetime.now(ZONE)
            today = now.date()
            current_time = now.time().replace(second=0, microsecond=0, tzinfo=None)
            print(f'Now: {now:%d-%m-%y %H:%M %Z}')
            if not all((args.mode, args.day, args.start, args.end)):
                print('Enter q at any prompt to leave.')
            if args.day:
                day = parse_day(args.day, today)
            elif mode == 'evening' and date.fromisoformat(coverage['from']) <= today <= date.fromisoformat(coverage['to']):
                day = today
                print(f'Planning for today, {display_day(today)}.')
            else:
                day = choose_query_day(today, coverage)
            validate_schedule(data, day)
            if mode == 'day':
                start = clock(args.start) if args.start else time(8, 30)
                end = clock(args.end) if args.end else time(22)
            else:
                default_start = current_time if day == today else time(8, 30)
                start = clock(args.start) if args.start else choose_time(
                    'Study from' if mode == 'evening' else 'Arrival', default_start.strftime('%H:%M'),
                    not_before=current_time if day == today else None)
                default_end = '22:00' if start < time(22) else '23:59'
                end = clock(args.end) if args.end else choose_time('Study until', default_end, after=start)
            if start >= end:
                raise ValueError('Study end must be later than arrival on the same day.')
            slots = search(data, day, 'day', start, end)
            results = search(data, day, mode, start, end)
            if mode == 'now':
                results.sort(key=lambda row: (-minutes(row[2]), row[0]))
            if mode != 'evening' or results:
                show_results(results, day, start, end, mode)
            else:
                print('\nNo single room covers the session. Checking room-change plans...')
            if mode != 'day':
                budget, preferred, kind = move_budget(minutes(start), minutes(end))
                if args.max_moves is not None:
                    budget = args.max_moves
                    preferred = min(preferred, budget)
                if not any(a == start and b == end and entry for _, a, b, entry in results):
                    print(f'{kind}: prefer up to {preferred} changes; maximum {budget}.')
                    plans = plan_session(slots, minutes(start), minutes(end), max_moves=budget,
                                         wait=15 if mode == 'now' else 0, transfer=args.move_minutes)
                    show_plans(plans, preferred=preferred, budget=budget)
                if mode == 'now':
                    soon = opening_soon(slots, minutes(start))
                    best_now = max((minutes(b) for _, _, b, entry in results if entry), default=minutes(start))
                    soon = [row for row in soon if minutes(row[2]) > best_now]
                    if soon:
                        show_results(soon, day, start, end, 'soon')
                        wait = minutes(soon[0][1]) - minutes(start)
                        print(f'Tip: waiting {wait} min opens {soon[0][0]} for a longer uninterrupted stay.')
                    elif results and any(b == end and entry for _, _, b, entry in results):
                        print('Tip: you can stay through the session without waiting or changing rooms.')
            if not repeat:
                return 0
            print()
            again = ask('Another search? y/n', 'n', lambda value: {'y': True, 'n': False}[value.lower()],
                        'Enter y or n.')
            if not again:
                return 0
            print()
    except (QuitSearch, KeyboardInterrupt, EOFError):
        print('\nClosed.')
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(color(f'Could not search: {exc}', '33'))
        if not args.demo and not args.data and not args.offline:
            print('Try again, or use --offline if you already have saved timetables.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
