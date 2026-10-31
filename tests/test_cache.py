import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from timetable_cache import RefreshError, digest, fetch, parse_ics, refresh


def lesson(start='16:30', end='18:00'):
    return {'room': 'A1.04', 'date': '2026-10-31', 'start': start, 'end': end}


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'cache.json'
        self.config = {
            'coverage': {'from': '2026-09-14', 'to': '2026-12-18',
                         'supsi_all_years': True, 'usi_at_supsi': True},
            'rooms': [{'id': 'A1.04', 'campus': 'Campus Est', 'floor': 1,
                       'sector': 'A', 'student_use_allowed': True}],
            'sources': [{'id': 'one', 'url': 'https://example.com/one', 'format': 'lesson-json'},
                        {'id': 'two', 'url': 'https://example.com/two', 'format': 'lesson-json'}]
        }
        self.remote = {'https://example.com/one': [lesson()], 'https://example.com/two': []}

    def download(self, url, old):
        return {'body': json.dumps(self.remote[url]), 'etag': 'test', 'last_modified': None}

    def test_persists_lessons_and_checks_every_source_on_every_launch(self):
        calls = []
        def recording(url, old):
            calls.append((url, old))
            return self.download(url, old)
        first, status = refresh(self.config, self.path, fetcher=recording)
        self.assertEqual(len(first['lessons']), 1)
        self.assertEqual(status['changed'], ['one', 'two'])
        second, status = refresh(self.config, self.path, fetcher=recording)
        self.assertEqual(first, second)
        self.assertEqual(status['changed'], [])
        self.assertFalse(status['bookings_changed'])
        self.assertEqual(len(calls), 4)
        second_run = dict(calls[2:])
        self.assertEqual(second_run['https://example.com/one']['sha256'], digest(json.dumps([lesson()])))

    def test_moves_and_deletions_replace_old_bookings(self):
        refresh(self.config, self.path, fetcher=self.download)
        self.remote['https://example.com/one'] = [lesson('18:00', '19:00')]
        updated, _ = refresh(self.config, self.path, fetcher=self.download)
        self.assertEqual(updated['lessons'][0]['start'], '18:00')
        self.remote['https://example.com/one'] = []
        updated, _ = refresh(self.config, self.path, fetcher=self.download)
        self.assertEqual(updated['lessons'], [])

    def test_partial_refresh_failure_preserves_entire_snapshot(self):
        refresh(self.config, self.path, fetcher=self.download)
        saved = self.path.read_bytes()
        self.remote['https://example.com/one'] = [lesson('18:00', '19:00')]
        def broken(url, old):
            if url.endswith('/two'):
                raise OSError('network unavailable')
            return self.download(url, old)
        with self.assertRaisesRegex(RefreshError, 'Previous saved lessons'):
            refresh(self.config, self.path, fetcher=broken)
        self.assertEqual(self.path.read_bytes(), saved)

    def test_offline_is_explicit_and_rejects_changed_configuration(self):
        with self.assertRaises(RefreshError):
            refresh(self.config, self.path, offline=True)
        refresh(self.config, self.path, fetcher=self.download)
        saved = self.path.read_bytes()
        data, status = refresh(self.config, self.path, offline=True)
        self.assertTrue(status['offline'])
        self.assertEqual(len(data['lessons']), 1)
        self.assertEqual(self.path.read_bytes(), saved)
        changed = copy.deepcopy(self.config)
        changed['sources'].pop()
        with self.assertRaises(RefreshError):
            refresh(changed, self.path, offline=True)

    def test_invalid_import_does_not_overwrite_cache(self):
        refresh(self.config, self.path, fetcher=self.download)
        saved = self.path.read_bytes()
        self.remote['https://example.com/one'] = [lesson('19:00', '18:00')]
        with self.assertRaises(RefreshError):
            refresh(self.config, self.path, fetcher=self.download)
        self.assertEqual(self.path.read_bytes(), saved)

    def test_http_304_uses_cached_body_and_sends_validators(self):
        old = {'body': 'saved', 'etag': '"v1"', 'last_modified': 'yesterday'}
        error = HTTPError('https://example.com', 304, 'Not Modified', {}, None)
        with patch('timetable_cache.urlopen', side_effect=error) as opener:
            result = fetch('https://example.com', old)
        self.assertEqual(result['body'], 'saved')
        headers = dict(opener.call_args.args[0].header_items())
        self.assertEqual(headers['If-none-match'], '"v1"')
        self.assertEqual(headers['If-modified-since'], 'yesterday')


class CalendarTests(unittest.TestCase):
    calendar = ('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:test\r\n'
                'DTSTART;TZID=Europe/Zurich:20261031T163000\r\n'
                'DTEND;TZID=Europe/Zurich:20261031T180000\r\n'
                'LOCATION:A1.04\r\nSUMMARY:Data\\, Science\r\n'
                'END:VEVENT\r\nEND:VCALENDAR\r\n')

    def test_imports_location_dates_timezone_and_escaped_title(self):
        event, = parse_ics(self.calendar)
        self.assertEqual(event['room'], 'A1.04')
        self.assertEqual(event['date'], '2026-10-31')
        self.assertEqual(event['start'], '16:30:00')
        self.assertEqual(event['title'], 'Data, Science')

    def test_cancelled_event_is_not_an_occupied_room(self):
        cancelled = self.calendar.replace('UID:test', 'UID:test\r\nSTATUS:CANCELLED')
        self.assertEqual(parse_ics(cancelled), [])

    def test_unsupported_recurrence_is_not_silently_ignored(self):
        recurring = self.calendar.replace('UID:test', 'UID:test\r\nRRULE:FREQ=WEEKLY')
        with self.assertRaisesRegex(RefreshError, 'Recurring'):
            parse_ics(recurring)

    def test_html_error_page_is_rejected(self):
        with self.assertRaises(RefreshError):
            parse_ics('<html>Login required</html>')


if __name__ == '__main__':
    unittest.main()
