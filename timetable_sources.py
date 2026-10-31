"""Discover published USI calendars and parse SUPSI Untis room grids."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SUPSI = 'https://www3.supsi.ch/inside/area_riservata_dti/orari/definitivi/'
USI = 'https://www.inf.usi.ch/it/informazioni-pratiche/orari'


class Page(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.links, self.tables, self.stack, self.cells = [], [], [], []
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'table':
            table = {'rows': []}
            if not self.stack:
                self.tables.append(table)
            self.stack.append(table)
        elif tag == 'tr' and self.stack:
            self.stack[-1]['rows'].append([])
        elif tag in ('td', 'th') and self.stack:
            if not self.stack[-1]['rows']:
                raise ValueError('Table cell without a row.')
            cell = {'text': '', 'rowspan': int(attrs.get('rowspan', 1)),
                    'colspan': int(attrs.get('colspan', 1)), 'depth': len(self.stack)}
            self.stack[-1]['rows'][-1].append(cell)
            self.cells.append(cell)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cells:
            self.cells.pop()
        elif tag == 'table' and self.stack:
            self.stack.pop()

    def handle_data(self, text):
        for cell in self.cells:
            cell['text'] += ' ' + text.strip()


def room_code(value):
    """Normalize punctuation/spacing, preserving Campus Ovest codes such as A11."""
    value = value.strip().upper()
    match = re.fullmatch(r'([ABCD])\s*(\d)\s*\.\s*(\d{2})', value)
    return ''.join((match[1], match[2], '.', match[3])) if match else value


def room_locations(value):
    # Multiple rooms in a single calendar event are all occupied.
    codes = re.findall(r'(?<![A-Z0-9])([ABCD]\s*\d\s*\.\s*\d{2})(?!\d)', value.upper())
    return [room_code(c) for c in codes] or [room_code(value)]


def supsi_rooms(navbar):
    match = re.search(r'var\s+rooms\s*=\s*(\[.*?\]);', navbar, re.S)
    if not match:
        raise ValueError('SUPSI room directory format changed.')
    names = json.loads(match[1])
    result = []
    for index, name in enumerate(names, 1):
        code = name.split()[0]
        if re.fullmatch(r'[BD]1\.\d{2}', code):
            result.append((index, code, name))
    if not result or len({r[1] for r in result}) != len(result):
        raise ValueError('SUPSI has no usable unique first-floor sector B/D room list.')
    return result


def parse_supsi(body, room, first, last, term):
    """Expand occupied grid cells; row spans may cross breaks and overlap groups."""
    if term not in ' '.join(body.split()):
        raise ValueError('SUPSI room page semester does not match the source directory.')
    if not re.search(r'(?<![A-Z0-9])' + re.escape(room) + r'(?!\d)', body):
        raise ValueError('SUPSI room page does not identify the requested room.')
    tables = Page(body).tables
    tables = [t for t in tables if t['rows'] and len(t['rows'][0]) in (6, 7)]
    if len(tables) != 1:
        raise ValueError('Cannot identify a unique SUPSI weekly room grid.')
    rows = tables[0]['rows']
    headers = rows[0][1:]
    if len(headers) != 5 or not all(word in cell['text'].lower() for word, cell in
                                   zip(('luned', 'marted', 'mercoled', 'gioved', 'venerd'), headers)):
        raise ValueError('Unsupported SUPSI weekday headers.')
    widths = [c['colspan'] for c in headers]
    if len(set(widths)) != 1:
        raise ValueError('Unequal weekday column widths.')
    width = widths[0]
    grid, placements = {}, []
    for r, cells in enumerate(rows):
        c = 0
        for cell in cells:
            while (r, c) in grid:
                c += 1
            height, span = cell['rowspan'], cell['colspan']
            if height < 1 or span < 1 or height > len(rows):
                raise ValueError('Invalid SUPSI cell span.')
            for y in range(r, r + height):
                for x in range(c, c + span):
                    if (y, x) in grid:
                        raise ValueError('Overlapping SUPSI grid cells.')
                    grid[y, x] = cell
            placements.append((r, c, cell))
            c += span
    expected_width = 1 + 5 * width
    if any((r, c) not in grid for r in range(len(rows)) for c in range(expected_width)):
        raise ValueError('Incomplete SUPSI weekly grid.')
    intervals, label_ranges = {}, {}
    for r, c, cell in placements:
        if r and c == 0:
            times = re.findall(r'\b\d{1,2}:\d{2}\b', cell['text'])
            if len(times) != 2:
                raise ValueError('SUPSI period has no clear start and end.')
            a, b = (f'{int(t.split(":")[0]):02}:{t.split(":")[1]}' for t in times)
            if a >= b:
                raise ValueError('Invalid SUPSI period times.')
            for y in range(r, r + cell['rowspan']):
                intervals[y] = (a, b)
                label_ranges[y] = (r, r + cell['rowspan'])
    patterns = []
    for r, c, cell in placements:
        title = ' '.join(cell['text'].split())
        if r == 0 or c == 0 or not title:
            continue
        end_row = r + cell['rowspan'] - 1
        if r not in intervals or end_row not in intervals:
            raise ValueError('Lesson outside SUPSI time grid.')
        if label_ranges[r][0] != r or label_ranges[end_row][1] != end_row + 1:
            raise ValueError('Unsupported partial-period SUPSI lesson.')
        weekday = (c - 1) // width
        if weekday >= 5 or (c + cell['colspan'] - 2) // width != weekday:
            raise ValueError('SUPSI lesson spans multiple weekdays.')
        patterns.append((weekday, intervals[r][0], intervals[end_row][1], title))
    result = []
    day, end = date.fromisoformat(first), date.fromisoformat(last)
    while day <= end:
        for weekday, start, finish, title in patterns:
            if day.weekday() == weekday:
                result.append({'room': room, 'date': day.isoformat(), 'start': start,
                               'end': finish, 'title': title})
        day += timedelta(days=1)
    return result


def discover(read, report=lambda message: None):
    """Follow every published Bachelor/Master, semester/year and calendar link."""
    from timetable_cache import cached_lessons
    report('Reading the USI programme directory…')
    directory = read('usi-directory', USI)['body']
    programme_links = {}
    for link in Page(directory).links:
        match = re.search(r'/(?:educations|offerte-formative)/(\d+)/([^/]+)/(?:schedules|piano-orari)$', link)
        if match and ('bachelor' in match[2] or 'master' in match[2]):
            if urlparse(link).hostname != 'search.usi.ch':
                raise ValueError('Unexpected USI timetable host.')
            programme_links[match[1]] = link
    if not {'30', '102', '22'} <= programme_links.keys():
        raise ValueError('USI directory is missing Informatics/Data Science programmes.')

    def programme(item):
        programme_id, url = item
        body = read('usi-programme-' + programme_id, url)['body']
        years = {}
        for link in Page(body).links:
            match = re.search(r'/(?:educations|offerte-formative)/(\d+)/[^/]+/(?:schedules|piano-orari)/(\d+)/(\d+)$', link)
            if match and match[1] == programme_id:
                if urlparse(link).hostname != 'search.usi.ch':
                    raise ValueError('Unexpected USI calendar host.')
                years[(programme_id, match[2], match[3])] = link
        if not years:
            raise ValueError(f'USI programme {programme_id} has no published year links; coverage is unknown.')
        return years

    years = {}
    report(f"Checking {len(programme_links)} USI programme pages…")
    with ThreadPoolExecutor(max_workers=4) as pool:
        for found in pool.map(programme, programme_links.items()):
            years.update(found)

    def calendar(item):
        key, url = item
        source_id = 'usi-' + '-'.join(key)
        body = read(source_id + '-page', url)['body']
        links = [urljoin(url, link) for link in Page(body).links if link.endswith('/ics')]
        # Published subscription links use webcal://; fetch over verified HTTPS.
        links = sorted(set(re.sub(r'^webcal:', 'https:', link) for link in links))
        if len(links) != 1 or urlparse(links[0]).hostname != 'search.usi.ch':
            raise ValueError(f'Cannot identify one USI calendar export for {source_id}.')
        source = {'id': source_id, 'url': links[0], 'format': 'usi-ics'}
        entry = read(source_id, links[0])
        content = entry['body']
        name = re.search(r'^X-WR-CALNAME:(.*(?:\r?\n[ \t].*)*)', content, re.M)
        if not name:
            raise ValueError('USI calendar has no semester label.')
        term = re.search(r'\b(SA|SP)\s+(\d{4})', re.sub(r'\r?\n[ \t]', '', name[1]))
        if not term:
            raise ValueError('Unrecognized USI calendar semester.')
        lessons = cached_lessons(source, entry)
        if not lessons:
            raise ValueError(f'Empty USI calendar {source_id}; cannot establish date coverage.')
        return source, lessons, (term[1], int(term[2])), body

    calendars = []
    report(f"Checking {len(years)} programme/year pages and calendar exports…")
    with ThreadPoolExecutor(max_workers=4) as pool:
        calendars = list(pool.map(calendar, sorted(years.items())))

    report('Reading the SUPSI room directory and semester notes…')
    nav = read('supsi-directory', SUPSI + 'frames/navbar.htm')['body']
    title = read('supsi-title', SUPSI + 'frames/title.htm')['body']
    footer = read('supsi-footer', SUPSI + 'frames/fuss.htm')['body']
    term = re.search(r'SEMESTRE\s+(AUTUNNALE|PRIMAVERILE)\s+(\d{4})', title)
    if not term:
        raise ValueError('Cannot identify SUPSI current semester.')
    label = term[0]
    semester = ('SA' if term[1] == 'AUTUNNALE' else 'SP', int(term[2]))
    calendars = [c for c in calendars if c[2] == semester]
    # Every discovered programme must have a calendar for the shared semester.
    if {s['id'].split('-')[1] for s, _, _, _ in calendars} != set(programme_links):
        raise ValueError('SUPSI and USI do not yet publish a common semester for every programme.')
    events = [e for _, lessons, _, _ in calendars for e in lessons]
    first, last = min(e['date'] for e in events), max(e['date'] for e in events)
    week = re.findall(r'<option\s+value="(\d+)">([\d.]+)</option>', nav, re.I)
    if len(week) != 1:
        raise ValueError('Unsupported SUPSI weekly export selection.')
    d, m, y = map(int, week[0][1].split('.'))
    if not first <= date(y, m, d).isoformat() <= last:
        raise ValueError('SUPSI weekly export and USI semester dates differ.')
    inventory = {code: {'id': code, 'name': name, 'campus': 'Campus Est', 'floor': 1,
                         'sector': code[0], 'is_classroom': True}
                 for _, code, name in supsi_rooms(nav)}
    # USI also publishes first-floor D rooms absent from the SUPSI room directory.
    for _, _, _, body in calendars:
        if 'USI East Campus' not in body and 'Campus Est' not in body:
            continue
        guide = re.search(r'(?:Sector|settore)\s+D:\s*([^<\r\n]+)', body, re.I)
        if guide:
            for code in re.findall(r'\bD1\.\d{2}\b', guide[1]):
                inventory.setdefault(code, {'id': code, 'name': code + ' (USI)', 'campus': 'Campus Est',
                                            'floor': 1, 'sector': 'D', 'is_classroom': True, 'usi_only': True})
    for event in events:
        for code in room_locations(event['room']):
            if re.fullmatch(r'[BD]1\.\d{2}', code) and code not in inventory:
                raise ValueError(f'New room {code} needs inventory confirmation.')
    sources = [source for source, _, _, _ in calendars]
    for index, code, name in supsi_rooms(nav):
        sources.append({'id': 'supsi-' + code, 'url': SUPSI + f'r/{week[0][0]}/r{index:05}.htm',
                        'format': 'supsi-room', 'room': code, 'from': first, 'to': last, 'term': label})
    updated = re.search(r'ultimo aggiornamento:\s*([\d-]+\s+[\d:]+)', footer)
    return {'sources': sources, 'rooms': list(inventory.values()),
            'coverage': {'from': first, 'to': last, 'supsi_all_years': True, 'usi_at_supsi': True},
            'notes': ['SUPSI publishes a recurring weekly semester pattern; dated exceptions are not provided.',
                      'Search window is limited to the dated USI lessons in the common semester.',
                      'A timetable gap does not verify student permission, door access or unlisted bookings.'],
            'summary': {'usi_programmes': len(programme_links), 'usi_calendars': len(calendars),
                        'supsi_rooms': len(supsi_rooms(nav)), 'rooms': len(inventory),
                        'supsi_published_update': updated[1] if updated else 'not stated'}}
