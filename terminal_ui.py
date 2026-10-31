"""Small terminal components with a plain-text fallback."""
import os
import shutil
import sys
import threading
import time
from datetime import date, datetime, timedelta


class QuitSearch(Exception):
    pass


class BackToMenu(Exception):
    pass


def color(text, code):
    if sys.stdout.isatty() and os.environ.get('TERM') != 'dumb' and 'NO_COLOR' not in os.environ:
        return f'\033[{code}m{text}\033[0m'
    return text


def heading(subtitle='Find a room to study in'):
    print('\n' + color('CAMPUS EST / ROOMS', '1;36'))
    print(subtitle)
    print('Floor 1  /  Sectors A + B  /  Europe/Zurich\n')


class Progress:
    def __init__(self, label):
        self.label = label
        self.initial = label
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.animated = sys.stdout.isatty() and os.environ.get('TERM') != 'dumb'

    def __enter__(self):
        self.started = time.monotonic()
        if self.animated:
            self.thread = threading.Thread(target=self._animate, daemon=True)
            self.thread.start()
        else:
            print(self.label + '...', flush=True)
        return self

    def update(self, message):
        with self.lock:
            self.label = message.rstrip('.…')
        if not self.animated:
            print('  ' + self.label, flush=True)

    def _animate(self):
        frame = 0
        while not self.stop.is_set():
            with self.lock:
                label = self.label
            width = max(10, shutil.get_terminal_size().columns - 13)
            elapsed = int(time.monotonic() - self.started)
            glyph = '|/-\\'[frame % 4]
            print(f'\r\033[2K {glyph} {label[:width]}  {elapsed}s', end='', flush=True)
            frame += 1
            self.stop.wait(0.12)

    def __exit__(self, kind, value, traceback):
        self.stop.set()
        if self.animated:
            self.thread.join()
            print('\r\033[2K', end='')
        elapsed = time.monotonic() - self.started
        print(color(f'{"OK" if kind is None else "!"}  {self.initial} ({elapsed:.1f}s)',
                    '32' if kind is None else '33'), flush=True)


def ask(label, default, parse, error, *, allow_back=True):
    while True:
        answer = input(f'  {label} [{default}]: ').strip()
        if answer.lower() in ('q', 'quit', 'exit'):
            raise QuitSearch
        if allow_back and answer.lower() in ('b', 'back', 'menu'):
            raise BackToMenu
        try:
            return parse(answer or str(default))
        except (ValueError, KeyError):
            print('  ' + color(error, '33'))


def parse_day(value, today):
    if value.lower() in ('today', 'tomorrow'):
        return today + timedelta(days=value.lower() == 'tomorrow')
    try:
        return datetime.strptime(value, '%d-%m-%y').date()
    except ValueError:
        return date.fromisoformat(value)


def display_day(value):
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime('%d-%m-%y')


def parse_clock(value):
    return datetime.strptime(value, '%H:%M').time()


def choose_mode():
    print(color('What do you need?', '1'))
    print('  1  Plan my study session')
    print('  2  Find a room at my arrival')
    print('  3  All free periods in a day')
    print('  q  Quit\n')
    return ask('Choose', '1', lambda value: {'1': 'evening', '2': 'now', '3': 'day'}[value],
               'Choose 1, 2, 3 or q.', allow_back=False)


def choose_day(default, today, coverage):
    def parse(value):
        day = parse_day(value, today)
        if not date.fromisoformat(coverage['from']) <= day <= date.fromisoformat(coverage['to']):
            raise ValueError('Outside coverage')
        return day
    return ask('Date (DD-MM-YY)', display_day(default), parse,
               f"Use DD-MM-YY, today or tomorrow, within {display_day(coverage['from'])} to {display_day(coverage['to'])}.")


def choose_query_day(today, coverage):
    covered = date.fromisoformat(coverage['from']) <= today <= date.fromisoformat(coverage['to'])
    if covered:
        use_today = ask(f'Today, {display_day(today)}? y/n', 'y',
                        lambda value: {'y': True, 'n': False}[value.lower()], 'Enter y or n.')
        if use_today:
            return today
    else:
        print('Today is outside the published timetable dates. Choose another date.')
    default = min(max(today + timedelta(days=1), date.fromisoformat(coverage['from'])),
                  date.fromisoformat(coverage['to']))
    return choose_day(default, today, coverage)


def choose_time(label, default, *, after=None, not_before=None):
    def parse(value):
        result = parse_clock(value)
        if after is not None and result <= after:
            raise ValueError('End must follow start')
        if not_before is not None and result < not_before:
            raise ValueError('Arrival is in the past')
        return result
    hint = 'Use HH:MM'
    if after:
        hint += ' and an end later than arrival'
    if not_before:
        hint += f'; today starts no earlier than {not_before:%H:%M}'
    return ask(label, default, parse, hint + '.')


def duration(start, end):
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes:02}m' if hours else f'{minutes}m'


def show_results(results, day, start, end, mode):
    titles = {'evening': 'Free for your whole session', 'now': 'Free at arrival', 'day': 'Free periods',
              'soon': 'Worth waiting for / opening within 15 minutes'}
    print('\n' + color(titles[mode], '1;36'))
    print(f'{display_day(day)}  /  {start:%H:%M} - {end:%H:%M}\n')
    if not results:
        print('No matching rooms in this time window.')
        if mode == 'evening' and start.hour * 60 + start.minute >= 17 * 60 + 30:
            print('Evening entry requires arrival before 17:30.')
        else:
            print('Try another arrival time or search all daily gaps.')
        return
    compact = shutil.get_terminal_size().columns < 58
    if compact:
        print(f'{"Room":<12} {"Free from - until":<17} Entry')
        print('-' * 47)
    else:
        print(f'{"Room":<12} {"From":<7} {"Until":<7} {"Free for":<10} Entry')
        print('-' * 58)
    for room, left, right, entry in results:
        access = 'Before 17:30' if entry else 'Unavailable'
        if compact:
            line = f'{room:<12} {left:%H:%M} - {right:%H:%M}     {access}'
        else:
            line = f'{room:<12} {left:%H:%M}   {right:%H:%M}   {duration(left, right):<10} {access}'
        print(line if entry else color(line, '33'))
    count = len({r[0] for r in results})
    print(f'\n{count} {"room" if count == 1 else "rooms"} / {len(results)} {"gap" if len(results) == 1 else "gaps"}')
    print('Until is capped at your search end. Entry follows the 17:30 badge rule.')


def show_plans(plans, *, preferred, budget):
    from study_planner import clock
    print('\n' + color('Suggested study plans', '1;36'))
    if not plans:
        print(f'No complete plan found within {budget} room changes and the 17:30 entry cutoff.')
        print('Try a shorter session or check daily free periods.')
        return
    good = [plan for plan in plans if plan['moves'] <= preferred]
    plans = good or plans
    if not good:
        print(f'Fallback: these plans need {budget} room changes.')
    for index, plan in enumerate(plans, 1):
        changes = plan['moves']
        label = f'{changes} {"change" if changes == 1 else "changes"}'
        if plan['wait']:
            label += f" / wait {plan['wait']} min before starting"
        print(color(f'  {index}. {label}', '1'))
        for j, (room, a, b) in enumerate(plan['segments']):
            print(f'     {clock(a)} - {clock(b)}  {room}')
            if j < changes:
                print(f"     {plan['transfer']} min to change rooms")
        total = plan['study_minutes']
        print(f'     Study time: {total // 60}h {total % 60:02}m\n')
    print('All room entries are before 17:30. Transfer breaks are included above.')
