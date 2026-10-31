"""Small terminal components with a plain-text fallback."""
import os
import shutil
import sys
import threading
import time
from datetime import date, datetime, timedelta


class QuitSearch(Exception):
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


def ask(label, default, parse, error):
    while True:
        answer = input(f'  {label} [{default}]: ').strip()
        if answer.lower() in ('q', 'quit', 'exit'):
            raise QuitSearch
        try:
            return parse(answer or str(default))
        except (ValueError, KeyError):
            print('  ' + color(error, '33'))


def parse_day(value, today):
    if value.lower() in ('today', 'tomorrow'):
        return today + timedelta(days=value.lower() == 'tomorrow')
    return date.fromisoformat(value)


def parse_clock(value):
    return datetime.strptime(value, '%H:%M').time()


def choose_mode():
    print(color('What do you need?', '1'))
    print('  1  A room for my whole study session')
    print('  2  A room free when I arrive')
    print('  3  All free periods in a day')
    print('  q  Quit\n')
    return ask('Choose', '1', lambda value: {'1': 'evening', '2': 'now', '3': 'day'}[value],
               'Choose 1, 2, 3 or q.')


def choose_day(default, today, coverage):
    def parse(value):
        day = parse_day(value, today)
        if not date.fromisoformat(coverage['from']) <= day <= date.fromisoformat(coverage['to']):
            raise ValueError('Outside coverage')
        return day
    return ask('Date', default, parse,
               f"Use YYYY-MM-DD, today or tomorrow, within {coverage['from']} to {coverage['to']}.")


def choose_time(label, default, *, after=None):
    def parse(value):
        result = parse_clock(value)
        if after is not None and result <= after:
            raise ValueError('End must follow start')
        return result
    return ask(label, default, parse, 'Use HH:MM' + (' and an end later than arrival.' if after else '.'))


def duration(start, end):
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes:02}m' if hours else f'{minutes}m'


def show_results(results, day, start, end, mode):
    titles = {'evening': 'Free for your whole session', 'now': 'Free at arrival', 'day': 'Free periods'}
    print('\n' + color(titles[mode], '1;36'))
    print(f'{day:%a %d %b %Y}  /  {start:%H:%M} - {end:%H:%M}\n')
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
