"""Local user preferences, independent of the checkout and timetable cache."""
import json
import os
import re
from pathlib import Path

from terminal_ui import BackToMenu, ask, color, parse_clock
from timetable_cache import atomic_write

DEFAULTS = {'study_end': '22:00', 'min_study': 30, 'max_wait': 15, 'move_minutes': 2,
            'afternoon_moves': 2, 'full_day_preferred': 3, 'full_day_max': 4,
            'more_options': 'ask', 'animation': True, 'colors': True, 'priority': 'fewer_moves',
            'favorites': [], 'reminder_minutes': 5, 'reminder_sound': False}


def location():
    override = os.environ.get('ROOMFINDER_PREFERENCES')
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'campus-room-finder' / 'preferences.json'


def validate(values):
    if not isinstance(values, dict):
        raise ValueError('Preferences must contain named settings.')
    merged = {**DEFAULTS, **{k: v for k, v in values.items() if k in DEFAULTS}}
    parse_clock(merged['study_end'])
    bounds = {'min_study': (1, 180), 'max_wait': (0, 60), 'move_minutes': (0, 15),
              'afternoon_moves': (0, 4), 'full_day_preferred': (0, 4), 'full_day_max': (0, 4),
              'reminder_minutes': (0, 30)}
    for key, (low, high) in bounds.items():
        if type(merged[key]) is not int or not low <= merged[key] <= high:
            raise ValueError(f'Invalid preference: {key}')
    if merged['full_day_preferred'] > merged['full_day_max']:
        raise ValueError('Preferred changes exceed the full-day limit.')
    if merged['more_options'] not in ('ask', 'all', 'best'):
        raise ValueError('Invalid result display preference.')
    if merged['priority'] not in ('fewer_moves', 'more_study'):
        raise ValueError('Invalid recommendation priority.')
    if any(type(merged[k]) is not bool for k in ('animation', 'colors', 'reminder_sound')):
        raise ValueError('Invalid display preferences.')
    if (not isinstance(merged['favorites'], list) or len(merged['favorites']) > 50
            or any(not isinstance(r, str) or not re.fullmatch(r'[BD]1\.\d{2}', r) for r in merged['favorites'])):
        raise ValueError('Favorites must be sector B/D room IDs, such as B1.01 or D1.13.')
    merged['favorites'] = sorted(set(merged['favorites']))
    return merged


def load(path=None):
    path = location() if path is None else Path(path)
    if not path.exists():
        return dict(DEFAULTS)
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Unsupported preferences version.')
    return validate(data['preferences'])


def save(values, path=None):
    values = validate(values)
    atomic_write(location() if path is None else path, {'version': 1, 'preferences': values})
    return values


def number(label, current, low, high):
    def parse(value):
        result = int(value)
        if not low <= result <= high:
            raise ValueError('Outside limits')
        return result
    return ask(label, current, parse, f'Enter a number from {low} to {high}.')


def first_setup(values, path=None):
    print('\n' + color('Make roomfinder yours', '1;36'))
    print('Enter keeps the suggested value. More choices are in Settings.\n')
    updated = dict(values)
    try:
        updated['study_end'] = ask('Usually study until', values['study_end'],
                                  lambda value: parse_clock(value).strftime('%H:%M'), 'Use HH:MM.')
        updated['min_study'] = number('Minimum worthwhile stay (min)', values['min_study'], 1, 180)
        updated['max_wait'] = number('Maximum initial wait (min)', values['max_wait'], 0, 60)
        updated['move_minutes'] = number('Time to change rooms (min)', values['move_minutes'], 0, 15)
    except BackToMenu:
        print('Keeping the defaults. You can change them in Settings.')
        updated = dict(values)
    updated = save(updated, path)
    print('Preferences saved locally.\n')
    return updated


def settings(values, path=None):
    current = dict(values)
    labels = {'ask': 'Ask after the best plan', 'all': 'Show all', 'best': 'Best plan only'}
    while True:
        print('\n' + color('Settings / saved on this computer', '1;36'))
        print(f"  1  Default study end          {current['study_end']}")
        print(f"  2  Minimum study block        {current['min_study']} min")
        print(f"  3  Maximum initial wait        {current['max_wait']} min")
        print(f"  4  Time per room change        {current['move_minutes']} min")
        print(f"  5  Afternoon change limit      {current['afternoon_moves']}")
        print(f"  6  Full-day preferred changes  {current['full_day_preferred']}")
        print(f"  7  Full-day maximum changes    {current['full_day_max']}")
        print(f"  8  More results                {labels[current['more_options']]}")
        print(f"  9  Loading animation           {'On' if current['animation'] else 'Off'}")
        print(f" 10  Colors                      {'On' if current['colors'] else 'Off'}")
        priority = 'Fewer changes' if current['priority'] == 'fewer_moves' else 'More study time'
        print(f' 11  Recommendation priority     {priority}')
        print(f" 12  Favorite rooms              {', '.join(current['favorites']) or 'None'}")
        print(f" 13  Move reminder lead time      {current['reminder_minutes']} min")
        print(f" 14  Reminder sound              {'On' if current['reminder_sound'] else 'Off'}")
        print('  r  Restore defaults\n  b  Main menu\n  q  Quit\n')
        print('The 17:00 room-entry rule is fixed. Changes save immediately.')
        try:
            def selection(value):
                if value not in [str(n) for n in range(1, 15)] + ['r']:
                    raise ValueError('Unknown setting')
                return value
            selected = ask('Setting', 'b', selection, 'Choose 1-14, r, b or q.')
            updated = dict(current)
            if selected == 'r':
                updated = dict(DEFAULTS)
            elif selected == '1':
                updated['study_end'] = ask('Study until', current['study_end'],
                                          lambda v: parse_clock(v).strftime('%H:%M'), 'Use HH:MM.')
            elif selected in ('2', '3', '4', '5', '6', '7', '13'):
                key, low, high = {'2': ('min_study', 1, 180), '3': ('max_wait', 0, 60),
                                  '4': ('move_minutes', 0, 15), '5': ('afternoon_moves', 0, 4),
                                  '6': ('full_day_preferred', 0, 4), '7': ('full_day_max', 0, 4),
                                  '13': ('reminder_minutes', 0, 30)}[selected]
                updated[key] = number('New value', current[key], low, high)
                if key == 'full_day_preferred':
                    updated['full_day_max'] = max(updated['full_day_max'], updated[key])
                elif key == 'full_day_max':
                    updated['full_day_preferred'] = min(updated['full_day_preferred'], updated[key])
            elif selected == '8':
                print('  1 Ask for more  /  2 Show all  /  3 Best only')
                updated['more_options'] = ask('Result display', '1',
                                              lambda v: {'1': 'ask', '2': 'all', '3': 'best'}[v], 'Choose 1, 2 or 3.')
            elif selected == '11':
                print('  1 Fewer changes  /  2 More study time (less waiting)')
                updated['priority'] = ask('Priority', '1',
                                          lambda v: {'1': 'fewer_moves', '2': 'more_study'}[v], 'Choose 1 or 2.')
            elif selected == '12':
                def favorite_rooms(value):
                    rooms = [] if value == '-' else [r.strip().upper() for r in value.split(',')]
                    return validate({**current, 'favorites': rooms})['favorites']
                updated['favorites'] = ask('Rooms, comma-separated (- clears)', ', '.join(current['favorites']) or '-',
                                           favorite_rooms, 'Use B1.01, D1.13, ... or - to clear.')
            else:
                key = {'9': 'animation', '10': 'colors', '14': 'reminder_sound'}[selected]
                updated[key] = not current[key]
            # Commit to disk before applying in memory, so a failed save never
            # claims a preference will survive the next launch.
            current = save(updated, path)
            apply_display(current)
            print(color('Saved.', '32'))
        except BackToMenu:
            return current


def apply_display(values):
    import terminal_ui
    terminal_ui.ANIMATION_ENABLED = values['animation']
    terminal_ui.COLORS_ENABLED = values['colors']
