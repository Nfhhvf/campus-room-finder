"""Terminal classroom availability search. Python 3.11+, no dependencies."""
if __name__ == '__main__':
    import sys
    from app_updates import before_launch
    before_launch(__file__, sys.argv)

import argparse
import json
import sys
import preferences
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
from timetable_cache import refresh
from terminal_ui import (Progress, QuitSearch, BackToMenu, ask, choose_mode, choose_time,
                         color, heading, show_results, choose_query_day, parse_day, display_day, show_plans, show_choices, parse_clock)

from study_planner import minutes, recommend
from study_session import actions

ZONE = ZoneInfo('Europe/Zurich')
CUTOFF = time(17, 0)
ROOT = Path(__file__).resolve().parent


def clock(value):
    return time.fromisoformat(value)


def load_schedule(path, day):
    data = json.loads(Path(path).read_text())
    return validate_schedule(scope_schedule(data), day)


def scope_schedule(data):
    """Apply the current scope even to a cache created by an older version."""
    active = [r for r in data['rooms'] if r['campus'] == 'Campus Est' and r['floor'] == 1 and r['sector'] in ('B', 'D')]
    ids = {r['id'] for r in active}
    if not active:
        raise ValueError('No Campus Est first-floor sector B or D rooms in the loaded timetables.')
    summary = dict(data.get('summary', {}))
    if summary:
        summary.update(rooms=len(active), supsi_rooms=sum(not r.get('usi_only', False) for r in active))
    missing = sorted({'B', 'D'} - {r['sector'] for r in active})
    return {**data, 'rooms': active, 'lessons': [e for e in data['lessons'] if e['room'] in ids],
            'summary': summary, 'missing_sectors': missing}


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
            ('Campus Est', 1, 'B'), ('Campus Est', 1, 'D')
        } or room.get('is_classroom', room.get('student_use_allowed')) is not True:
            continue
        lessons = [e for e in data['lessons'] if e['room'] == room['id'] and e['date'] == day.isoformat()]
        slots = list(free_slots(lessons, start, end))
        if mode == 'evening':
            slots = [(a, b) for a, b in slots if a == start and b == end and start < CUTOFF]
        elif mode == 'now':
            slots = [(a, b) for a, b in slots if a == start]
        for a, b in slots:
            # The interface plans in minutes. Round conservatively so a lesson
            # ending at 14:30:30 never becomes a recommended 14:30 entry.
            first = a.hour * 60 + a.minute + bool(a.second or a.microsecond)
            last = b.hour * 60 + b.minute
            if first >= last or first >= 24 * 60:
                continue
            a, b = time(first // 60, first % 60), time(last // 60, last % 60)
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
    parser.add_argument('--settings', action='store_true', help='Open local preferences without loading timetables')
    parser.add_argument('--all-options', action='store_true', help='Show all ranked alternatives without asking')
    parser.add_argument('--mode', choices=['evening', 'now', 'day'])
    parser.add_argument('--date', dest='day', help='Study date as DD-MM-YY')
    parser.add_argument('--max-moves', type=int, choices=range(5), help='Override room-change limit (0-4)')
    parser.add_argument('--min-study', type=int, choices=range(1, 181), default=None, help='Override the minimum study block from Settings')
    parser.add_argument('--move-minutes', type=int, choices=range(16), default=None, help='Override the room-change time from Settings')
    parser.add_argument('--start')
    parser.add_argument('--end')
    args = parser.parse_args()
    try:
        try:
            prefs = preferences.load()
        except (ValueError, KeyError, TypeError, OSError) as exc:
            prefs = dict(preferences.DEFAULTS)
            print(f'Could not read saved preferences: {exc}. Using defaults; check Settings.')
        preferences.apply_display(prefs)
        heading()
        if args.settings:
            preferences.settings(prefs)
            return 0
        guided = sys.stdin.isatty() and not any((args.mode, args.day, args.start, args.end))
        if guided and not preferences.location().exists():
            prefs = preferences.first_setup(prefs)
            preferences.apply_display(prefs)
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
        data = scope_schedule(data)
        coverage = data['coverage']
        validate_schedule(data, date.fromisoformat(coverage['from']))
        summary = data.get('summary', {})
        if summary:
            print(f"{summary['rooms']} rooms / SUPSI + {summary['usi_programmes']} USI programmes")
        print(f"Dates: {display_day(coverage['from'])} to {display_day(coverage['to'])}")
        if data['missing_sectors']:
            print('Saved inventory is missing sector ' + ', '.join(data['missing_sectors']) + '. Refresh online to include it.')
        if data.get('notes'):
            print('SUPSI uses a weekly pattern; dated exceptions may be missing.')
        print('Published lesson gaps only. Room access and unlisted bookings are not verified.\n')
        repeat = guided
        excluded_by_day = {}
        while True:
            try:
                mode = args.mode or choose_mode()
                if mode == 'settings':
                    prefs = preferences.settings(prefs)
                    preferences.apply_display(prefs)
                    continue
                min_study = prefs['min_study'] if args.min_study is None else args.min_study
                transfer = prefs['move_minutes'] if args.move_minutes is None else args.move_minutes
                now = datetime.now(ZONE)
                today = now.date()
                current_time = now.time().replace(second=0, microsecond=0, tzinfo=None)
                print(f'Now: {now:%d-%m-%y %H:%M %Z}')
                if not all((args.mode, args.day, args.start, args.end)):
                    print('b  Back to menu  /  q  Quit')
                if args.day:
                    day = parse_day(args.day, today)
                elif mode == 'evening' and date.fromisoformat(coverage['from']) <= today <= date.fromisoformat(coverage['to']):
                    day = today
                    print(f'Planning for today, {display_day(today)}.')
                else:
                    day = choose_query_day(today, coverage)
                validate_schedule(data, day)
                if mode == 'day':
                    start = parse_clock(args.start) if args.start else max(time(8, 30), current_time) if day == today else time(8, 30)
                    end = parse_clock(args.end) if args.end else parse_clock(prefs['study_end'])
                else:
                    default_start = current_time if day == today else time(8, 30)
                    start = parse_clock(args.start) if args.start else choose_time(
                        'Study from' if mode == 'evening' else 'Arrival', default_start.strftime('%H:%M'),
                        not_before=current_time if day == today else None)
                    default_end = prefs['study_end'] if start < parse_clock(prefs['study_end']) else '23:59'
                    end = parse_clock(args.end) if args.end else choose_time('Study until', default_end, after=start)
                if start >= end:
                    if mode == 'day' and not args.start and not args.end:
                        if day == today and current_time >= end:
                            print('Today’s study window has ended. Choose another date or change the end time in Settings.')
                        else:
                            print('Daily overview starts at 08:30. Choose a later default end time in Settings.')
                        if repeat:
                            raise BackToMenu
                        return 0
                    raise ValueError('Study end must be later than arrival on the same day.')
                start_min, end_min = minutes(start), minutes(end)
                explicit_window = mode != 'day' or args.start is not None or args.end is not None
                minimum = min(min_study, end_min - start_min) if explicit_window else min_study
                blocked = excluded_by_day.setdefault(day, set())
                def get_slots(lower):
                    window_start = time(lower // 60, lower % 60)
                    return [row for row in search(data, day, 'day', window_start, end) if row[0] not in blocked]
                slots = get_slots(start_min)
                result = recommend(slots, start_min, end_min, prefs, mode=mode, minimum=minimum,
                                   transfer=transfer, budget=args.max_moves)
                priority_label = 'fewer moves first' if prefs['priority'] == 'fewer_moves' else 'more study time first'
                print(f'Practical options / at least {minimum} min per room / {priority_label}')
                if blocked:
                    print('Occupied rooms excluded for this date: ' + ', '.join(sorted(blocked)))
                options = result['options']
                presentation = {'interactive': repeat and prefs['more_options'] == 'ask',
                                'all_options': args.all_options or prefs['more_options'] == 'all'}
                def render(group):
                    if group and all(p['moves'] == 0 and p['wait'] == 0 and p.get('complete') for p in group):
                        rows = [(p['segments'][0][0], time(p['segments'][0][1] // 60, p['segments'][0][1] % 60),
                                 time(p['segments'][0][2] // 60, p['segments'][0][2] % 60), True) for p in group]
                        show_results(rows, day, start, end, 'evening')
                    else:
                        if group and any(not p.get('complete') for p in group):
                            print('This option starts later or covers only part of the requested window.')
                        show_plans(group, preferred=result['preferred'], budget=result['budget'], min_study=minimum)
                if options:
                    first = options[0]
                    if first.get('complete') and first['moves'] == 0:
                        print(f"Best strategy: stay in {first['segments'][0][0]} until {end:%H:%M}. No moves.")
                    else:
                        print('Recommended journey / includes the next room and time for every connection.')
                    if any(room in prefs['favorites'] for room, _, _ in first['segments']):
                        print('Your favorites helped choose between otherwise suitable options.')
                    show_choices(options, render, **presentation)
                else:
                    print('No useful itinerary fits your wait, move, minimum-stay and entry limits.')
                    print('Try another start time, or change your preferences in Settings.')
                hidden = sum(row[3] and minutes(row[2]) - minutes(row[1]) < minimum for row in slots)
                if hidden:
                    print(f'Skipped {hidden} gaps shorter than {minimum} min.')
                if not repeat:
                    return 0
                actions(data, day, start, end, prefs, result, blocked, get_slots)
            except BackToMenu:
                args.mode = None
                print('\nBack to main menu.\n')
                continue
    except (QuitSearch, KeyboardInterrupt, EOFError):
        print('\nClosed.')
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(color(f'Could not search: {exc}', '33'))
        if not args.demo and not args.data and not args.offline:
            print('Try again, or use --offline if you already have saved timetables.')
            print('Preferences are available without timetable downloads: roomfinder --settings')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
