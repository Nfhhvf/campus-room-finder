"""Transactional timetable refresh with conditional HTTP and persistent lessons."""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor


class RefreshError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def fetch(url, previous):
    """Return text and HTTP validators. Never disable TLS verification."""
    if urlparse(url).scheme != 'https':
        raise RefreshError('Timetable sources must use HTTPS.')
    headers = {'User-Agent': 'CampusEstRoomFinder/0.1', 'Cache-Control': 'no-cache'}
    if previous:
        if previous.get('etag'):
            headers['If-None-Match'] = previous['etag']
        if previous.get('last_modified'):
            headers['If-Modified-Since'] = previous['last_modified']
    try:
        with urlopen(Request(url, headers=headers), timeout=25) as response:
            if urlparse(response.url).scheme != 'https':
                raise RefreshError('Timetable redirected to an insecure URL.')
            payload = response.read(10_000_001)
            if len(payload) > 10_000_000:
                raise RefreshError('Timetable exceeds the 10 MB source limit.')
            encoding = response.headers.get_content_charset()
            if not encoding:
                declaration = re.search(br'charset=["\s]*([\w-]+)', payload[:2000], re.I)
                encoding = declaration[1].decode('ascii') if declaration else 'utf-8-sig'
            return {'body': payload.decode(encoding),
                    'etag': response.headers.get('ETag'),
                    'last_modified': response.headers.get('Last-Modified')}
    except HTTPError as exc:
        if exc.code == 304 and previous:
            return dict(previous)
        raise RefreshError(f'Timetable HTTP error: {exc.code}') from exc
    except (URLError, OSError, UnicodeError) as exc:
        raise RefreshError(f'Timetable download failed: {exc}') from exc


def unescape(value):
    return re.sub(r'\\([nN,;\\])', lambda m: '\n' if m[1].lower() == 'n' else m[1], value)


def ics_datetime(key, value):
    if 'VALUE=DATE' in key or not re.fullmatch(r'\d{8}T\d{6}Z?', value):
        raise RefreshError('Unsupported calendar date format; cannot infer occupancy.')
    parsed = datetime.strptime(value.rstrip('Z'), '%Y%m%dT%H%M%S')
    if value.endswith('Z'):
        zone = timezone.utc
    else:
        match = re.search(r'(?:^|;)TZID=([^;]+)', key)
        if not match:
            raise RefreshError('Calendar lesson has no explicit timezone.')
        zone = ZoneInfo(match[1].strip('"'))
    return parsed.replace(tzinfo=zone).astimezone(ZoneInfo('Europe/Zurich'))


def parse_ics(body):
    """USI exports dated events. Reject recurrence rather than silently omit it."""
    lines = re.sub(r'\r?\n[ \t]', '', body).splitlines()
    if 'BEGIN:VCALENDAR' not in lines or 'END:VCALENDAR' not in lines:
        raise RefreshError('Source is not a complete calendar.')
    events, current = [], None
    for line in lines:
        if line == 'BEGIN:VEVENT':
            if current is not None:
                raise RefreshError('Malformed nested calendar event.')
            current = {}
        elif line == 'END:VEVENT':
            if current is None:
                raise RefreshError('Malformed calendar event ending.')
            if current.get('STATUS', ('', ''))[1] != 'CANCELLED':
                if any(k in current for k in ('RRULE', 'RDATE', 'EXDATE', 'RECURRENCE-ID')):
                    raise RefreshError('Recurring calendar rules require an importer update.')
                for field in ('DTSTART', 'DTEND', 'LOCATION'):
                    if field not in current:
                        raise RefreshError(f'Calendar lesson is missing {field}.')
                start = ics_datetime(*current['DTSTART'])
                end = ics_datetime(*current['DTEND'])
                if end <= start or end.date() != start.date():
                    raise RefreshError('Unsupported overnight or invalid lesson interval.')
                events.append({'room': unescape(current['LOCATION'][1]).strip(),
                               'date': start.date().isoformat(),
                               'start': start.time().isoformat(), 'end': end.time().isoformat(),
                               'title': unescape(current.get('SUMMARY', ('', ''))[1])})
            current = None
        elif current is not None and ':' in line:
            key, value = line.split(':', 1)
            name = key.split(';', 1)[0]
            if name in current:
                raise RefreshError(f'Duplicate calendar property: {name}.')
            current[name] = (key, value)
    if current is not None:
        raise RefreshError('Incomplete calendar event.')
    return events


def parse_lessons(source, body):
    if source['format'] == 'supsi-room':
        from timetable_sources import parse_supsi
        return parse_supsi(body, source['room'], source['from'], source['to'], source['term'])
    if source['format'] == 'usi-ics':
        return parse_ics(body)
    if source['format'] == 'lesson-json':
        lessons = json.loads(body)
        if not isinstance(lessons, list):
            raise RefreshError('Lesson JSON must contain a list of dated lessons.')
        for lesson in lessons:
            start = datetime.fromisoformat(lesson['date'] + 'T' + lesson['start'])
            end = datetime.fromisoformat(lesson['date'] + 'T' + lesson['end'])
            if not isinstance(lesson['room'], str) or not lesson['room'] or end <= start:
                raise RefreshError('Invalid lesson JSON interval or room.')
        return lessons
    raise RefreshError(f"No importer for source format: {source['format']}")


def signature(config):
    return digest(json.dumps(config, sort_keys=True))


def refresh(config, cache_path, *, offline=False, fetcher=fetch, progress=None):
    """Publish a whole new snapshot only after every configured source succeeds."""
    cache_path = Path(cache_path)
    previous = json.loads(cache_path.read_text()) if cache_path.exists() else None
    if previous and previous.get('version') != 1:
        raise RefreshError('Unsupported cache version.')
    if offline:
        if not previous or previous['config_signature'] != signature(config):
            raise RefreshError('No saved lessons for this configuration; connect first.')
        return previous['schedule'], {'offline': True, 'checked_at': previous['checked_at']}
    original_signature = signature(config)
    report = progress or (lambda message: None)
    old_sources = previous.get('source_cache', {}) if previous else {}
    new_sources, changed = {}, []

    def read(source_id, url):
        if source_id in new_sources:
            if new_sources[source_id]['source']['url'] != url:
                raise RefreshError('Duplicate source ID points to different URLs.')
            return new_sources[source_id]
        try:
            old = old_sources.get(source_id)
            if old and (old['source']['url'] != url or digest(old['body']) != old['sha256']):
                old = None
            downloaded = fetcher(url, old)
            checksum = digest(downloaded['body'])
            entry = {**downloaded, 'sha256': checksum, 'source': {'url': url}}
            new_sources[source_id] = entry
            if not old or old['sha256'] != checksum:
                changed.append(source_id)
            return entry
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise RefreshError(f'{source_id}: {exc}. Previous saved lessons were kept unchanged.') from exc

    if config.get('discovery') == 'campus-est':
        from timetable_sources import discover
        try:
            config = discover(read, report)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise RefreshError(f'Discovery failed: {exc}. Previous saved lessons were kept unchanged.') from exc
    sources = config['sources']
    ids = [s['id'] for s in sources]
    if not ids or len(ids) != len(set(ids)):
        raise RefreshError('Configure a nonempty list of uniquely identified sources.')
    lessons = []
    room_ids = {r['id'] for r in config['rooms']}

    def import_source(source):
        source_id = source['id']
        try:
            body = read(source_id, source['url'])['body']
            # Rebuild each source completely, so deletions/cancellations disappear.
            imported = parse_lessons(source, body)
            result = []
            from timetable_sources import room_locations
            for lesson in imported:
                location = source.get('room_aliases', {}).get(lesson['room'], lesson['room'])
                for room in room_locations(location):
                    if room in room_ids:
                        result.append({**lesson, 'room': room, 'source': source_id})
            return result
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise RefreshError(f'{source_id}: {exc}. Previous saved lessons were kept unchanged.') from exc
    report(f'Importing and combining {len(sources)} classroom timetables…')
    with ThreadPoolExecutor(max_workers=4) as pool:
        for imported in pool.map(import_source, sources):
            lessons.extend(imported)
    lessons = sorted({json.dumps(e, sort_keys=True): e for e in lessons}.values(),
                     key=lambda e: (e['date'], e['room'], e['start'], e['end'], e['source']))
    checked_at = datetime.now(timezone.utc).isoformat()
    schedule = {'schema_version': 1, 'sources': [s['url'] for s in sources],
                'coverage': config['coverage'], 'rooms': config['rooms'], 'lessons': lessons}
    schedule['notes'] = config.get('notes', [])
    schedule['summary'] = config.get('summary', {})
    snapshot = {'version': 1, 'config_signature': original_signature, 'checked_at': checked_at,
                'source_cache': new_sources, 'schedule': schedule}
    atomic_write(cache_path, snapshot)
    return schedule, {'offline': False, 'checked_at': checked_at,
                      'checked': len(new_sources), 'changed': sorted(changed),
                      'bookings_changed': not previous or previous['schedule']['lessons'] != lessons}
