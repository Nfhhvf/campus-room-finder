"""Actions for a selected study itinerary; occupancy reports last for this run."""
import select
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import preferences
from study_planner import CUTOFF, clock, minutes, recommend
from terminal_ui import BackToMenu, QuitSearch, ask, color, display_day

ZONE = ZoneInfo('Europe/Zurich')


def show_timeline(plan, day):
    print('\n' + color(f'Your timeline / {display_day(day)}', '1;36'))
    if not plan.get('complete', True):
        print('This option starts later or covers only part of your requested window.')
    segments = plan['segments']
    if plan['wait']:
        first = segments[0][1]
        print(f'  {clock(first - plan["wait"])} - {clock(first)}  WAIT')
    for i, (room, start, end) in enumerate(segments):
        print(f'  {clock(start)} - {clock(end)}  STUDY  {room}')
        if i + 1 < len(segments):
            target, arrival, _ = segments[i + 1]
            print(f'  {clock(end)} - {clock(arrival)}  MOVE   {room} -> {target}')
    total = plan['study_minutes']
    print(f"{total // 60}h {total % 60:02}m studying / {plan['moves']} room changes")
    if plan['moves']:
        print('Follow the move times: entering the next room later may miss the 17:00 cutoff.')


def choose_room(data, default):
    known = {r['id'] for r in data['rooms']}
    def parse(value):
        if value == '?':
            print('  ' + ', '.join(sorted(known)))
            raise ValueError('Choose a room')
        room = value.strip().upper()
        if room not in known:
            raise ValueError('Unknown room')
        return room
    return ask('Room (? lists rooms)', default, parse, 'Enter a published sector B or D room ID.')


def show_room_details(data, room, day, reference, plan, blocked, prefs):
    info = next(r for r in data['rooms'] if r['id'] == room)
    print('\n' + color(info.get('name', room), '1;36'))
    print(f'{display_day(day)} / reference time {clock(reference)} / sector {info["sector"]}, floor 1')
    print('Favorite: ' + ('Yes' if room in prefs.get('favorites', []) else 'No'))
    if room in blocked:
        print('You marked this room occupied; it is excluded for this session date.')
    events = sorted((e for e in data['lessons'] if e['room'] == room and e['date'] == day.isoformat()),
                    key=lambda e: (e['start'], e['end']))
    seen, upcoming = set(), []
    for event in events:
        left = time.fromisoformat(event['start'])
        right = time.fromisoformat(event['end'])
        # Use seconds when determining occupancy at the displayed reference minute.
        point = time(reference // 60, reference % 60)
        key = (event['start'], event['end'], event.get('title', 'Scheduled lesson'))
        if right <= point or key in seen:
            continue
        seen.add(key)
        upcoming.append((event, left, right))
    if upcoming:
        for event, left, right in upcoming[:3]:
            point = time(reference // 60, reference % 60)
            label = 'In progress' if left <= point < right else 'Next lesson'
            source = event.get('source', '')
            source = 'SUPSI' if source.startswith('supsi') else 'USI' if source.startswith('usi') else 'Timetable'
            title = ' '.join(str(event.get('title') or 'Scheduled lesson').split())[:120]
            print(f'{label}: {left:%H:%M} - {right:%H:%M} / {title} / {source}')
    else:
        print('No later lesson appears in the loaded timetables for this date.')
    for i, (selected, a, b) in enumerate(plan['segments']):
        if selected != room:
            continue
        print(f'Chosen study block: {clock(a)} - {clock(b)}.')
        if plan.get('complete') and plan.get('moves') == 0:
            print('Why this room: it covers the entire requested session without a move or initial wait.')
        elif i + 1 < len(plan['segments']):
            target, entry, _ = plan['segments'][i + 1]
            print(f'Why this room: connects to {target}; leave at {clock(b)}, enter at {clock(entry)}.')
        else:
            print(f'Why this room: it is the final study block, through {clock(b)}.')
    print('Published timetables only; unscheduled bookings and actual door access are not verified.')


def reminder_events(plan, day, lead):
    events = []
    if plan['wait']:
        room, entry, _ = plan['segments'][0]
        events.append((datetime.combine(day, time(entry // 60, entry % 60), ZONE), f'Planned study start: {room}, {clock(entry)}.'))
    for i, (_, _, leave) in enumerate(plan['segments'][:-1]):
        target, arrival, _ = plan['segments'][i + 1]
        deadline = datetime.combine(day, time(leave // 60, leave % 60), ZONE)
        if lead:
            events.append((deadline - timedelta(minutes=lead), f'Move in {lead} min: leave at {clock(leave)} for {target}.'))
        events.append((deadline, f'Move now: {target}, planned entry {clock(arrival)}.'))
    finish = plan['segments'][-1][2]
    events.append((datetime.combine(day, time(finish // 60, finish % 60), ZONE), 'Your planned study session has ended.'))
    return sorted(events, key=lambda e: e[0])


def wait_for_input(seconds):
    ready, _, _ = select.select([sys.stdin], [], [], seconds)
    return sys.stdin.readline() if ready else None


def watch_plan(plan, day, prefs, *, now_fn=None, waiter=wait_for_input):
    now_fn = now_fn or (lambda: datetime.now(ZONE))
    now = now_fn()
    if day != now.date():
        print('Start reminders on the date of this plan. No background alarm was installed.')
        return
    if minutes(now.time()) >= plan['segments'][-1][2]:
        print('This plan has already ended.')
        return
    if not sys.stdin.isatty():
        print('Reminders require an interactive terminal.')
        return
    events = [(when, message) for when, message in reminder_events(plan, day, prefs['reminder_minutes']) if when >= now]
    print('\nReminders active while this view stays open. Enter returns to actions; b opens the menu; q quits.')
    print('Timers follow this saved plan; they do not check room occupancy or new timetable edits.')
    if not plan['moves']:
        print('No room changes planned; reminders cover the study start (if waiting) and session end.')
    for room, start, end in plan['segments']:
        if end > minutes(now.time()):
            print(f'Next/current planned room: {room} / {clock(start)} - {clock(end)}')
            break
    for _, _, leave in plan['segments'][:-1]:
        gap = leave - minutes(now.time())
        if 0 <= gap <= prefs['reminder_minutes']:
            print(f'Upcoming move at {clock(leave)} (in about {gap} min).')
    try:
        while events:
            now = now_fn()
            while events and events[0][0] <= now:
                _, message = events.pop(0)
                print(('\a' if prefs['reminder_sound'] else '') + '\n' + color(message, '1;33'), flush=True)
            if not events:
                break
            answer = waiter(min(30, max(0.1, (events[0][0] - now).total_seconds())))
            if answer is not None:
                if answer.strip().lower() in ('q', 'quit', 'exit'):
                    raise QuitSearch
                if answer.strip().lower() in ('b', 'back', 'menu'):
                    raise BackToMenu
                break
    except (KeyboardInterrupt, OSError, ValueError):
        pass
    print('Reminders stopped. No alarms remain running.')


def actions(data, day, start, end, prefs, result, blocked, get_slots, *, now_fn=None):
    """Return to the caller's main menu on b; q keeps the usual global quit."""
    now_fn = now_fn or (lambda: datetime.now(ZONE))
    options = list(result['options'])
    active = options[0] if options else None
    consumed_moves = 0
    while True:
        print('\n' + color('What next?', '1'))
        print('  o  Room occupied / find another plan\n  d  Room details\n  f  Add/remove a favorite')
        print('  p  Plan timeline\n  c  Choose another option\n  r  Move reminders')
        print('  u  Clear occupied-room reports\n  b  Main menu / new search\n  q  Quit')
        def parse(value):
            if value.lower() not in ('o', 'd', 'f', 'p', 'c', 'r', 'u'):
                raise ValueError('Unknown action')
            return value.lower()
        action = ask('Action', 'b', parse, 'Choose o, d, f, p, c, r, u, b or q.')
        now = now_fn()
        point = minutes(now.time())
        default = (next((room for room, a, b in active['segments'] if day == now.date() and a <= point < b),
                        active['segments'][0][0]) if active else data['rooms'][0]['id'])
        if action in ('p', 'r', 'c') and active is None:
            print('No active plan. Choose another search or clear an occupied-room report.')
            continue
        if action == 'p':
            show_timeline(active, day)
        elif action == 'r':
            watch_plan(active, day, prefs, now_fn=now_fn)
        elif action == 'c':
            if day < now.date() or (day == now.date() and point > minutes(start)):
                print('These alternatives were planned earlier. Start a new search for the current time; use o if a room is occupied.')
                continue
            for i, plan in enumerate(options, 1):
                route = ' -> '.join(room for room, _, _ in plan['segments'])
                print(f"  {i}  {route} / {plan['moves']} changes / wait {plan['wait']} min")
            selected = preferences.number('Use option', 1, 1, len(options))
            active = options[selected - 1]
            show_timeline(active, day)
        elif action == 'f':
            room = choose_room(data, default)
            favorites = set(prefs['favorites'])
            if room in favorites:
                favorites.remove(room)
            else:
                favorites.add(room)
            try:
                saved = preferences.save({**prefs, 'favorites': sorted(favorites)})
            except (ValueError, OSError) as exc:
                print(f'Could not save favorites: {exc}')
                continue
            prefs.update(saved)
            print(f"{room} {'added to' if room in favorites else 'removed from'} favorites. Applied to your next search/replan.")
        elif action == 'd':
            room = choose_room(data, default)
            entry = next((a for r, a, _ in active['segments'] if r == room), minutes(start)) if active else minutes(start)
            reference = max(entry, point) if day == now.date() else entry
            reference = min(reference, 23 * 60 + 59)
            show_room_details(data, room, day, reference, active or {'segments': []}, blocked, prefs)
        else:
            if action == 'u':
                blocked.clear()
                print('Occupied-room reports cleared for this date. Start a new search to restore those rooms.')
                continue
            room = choose_room(data, default)
            if day < now.date():
                print('Cannot replan a session in the past. Start a new search.')
                continue
            blocked.add(room)
            print(f'{room} excluded for {display_day(day)} until you clear reports or close the program.')
            earliest = max(minutes(start), point + bool(now.second or now.microsecond)) if day == now.date() else minutes(start)
            options = [p for p in options if not any(r in blocked and b > earliest for r, _, b in p['segments'])]
            if active and not any(r == room and b > earliest for r, _, b in active['segments']):
                print('Your active plan does not need that room for the remaining session.')
                continue
            if earliest >= minutes(end):
                active = None
                options = []
                print('The requested session has ended. Start a new search.')
                continue
            if earliest + result['transfer'] >= CUTOFF:
                active = None
                options = []
                print('No new room entry is possible before 17:00 with your walking time. No unsafe move was suggested.')
                continue
            used = 0
            if day == now.date() and point >= minutes(start):
                inside = ask('Already studying inside a room? y/n', 'n',
                             lambda v: {'y': True, 'n': False}[v.lower()], 'Enter y or n.')
                if inside:
                    assumed = sum(a <= point for _, a, _ in active['segments'][1:]) if active else 0
                    used = preferences.number('Room changes already made', min(consumed_moves + assumed, result['budget']), 0, result['budget']) + 1
            remaining = result['budget'] - used
            if remaining < 0:
                active = None
                options = []
                print('Another move would exceed your session change limit.')
                continue
            arrival = earliest + result['transfer']
            print(f'Replanning from {clock(arrival)}; {result["transfer"]} min to reach an alternative room.')
            rows = [row for row in get_slots(arrival) if row[0] not in blocked]
            replacement = recommend(rows, arrival, minutes(end), prefs, mode='now', minimum=result['minimum'],
                                    transfer=result['transfer'], budget=remaining, preferred=min(result['preferred'], remaining))
            options = replacement['options']
            consumed_moves = used
            active = options[0] if options else None
            if active:
                show_timeline(active, day)
                print('Alternative selected from the loaded timetables; an unlisted booking is still possible.')
            else:
                print('No practical alternative fits the remaining time, occupied reports and move limit.')
