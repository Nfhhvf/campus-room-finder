import unittest
import tempfile
from pathlib import Path
from datetime import date, time
from timetable_sources import Page, discover, parse_supsi, room_code, room_locations, supsi_rooms
from timetable_cache import refresh
from rooms import search


def grid():
    header = '<tr><td></td>' + ''.join(f'<td colspan="12">{d}</td>' for d in
                                      ('lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì')) + '</tr>'
    label1 = '<td rowspan="2"><table><tr><td>8:30</td></tr><tr><td>9:15</td></tr></table></td>'
    label2 = '<td rowspan="2"><table><tr><td>9:30</td></tr><tr><td>10:15</td></tr></table></td>'
    busy = '<td rowspan="4" colspan="12"><table><tr><td>Course</td><td>Year 3</td></tr></table></td>'
    empty = '<td rowspan="4" colspan="12"><table><tr><td></td></tr></table></td>'
    split = '<td rowspan="2" colspan="6">Lab group 1</td><td rowspan="2" colspan="6">Lab group 2</td>'
    row1 = '<tr>' + label1 + busy + split + empty * 3 + '</tr>'
    row3 = '<tr>' + label2 + '<td rowspan="2" colspan="12"></td></tr>'
    return 'B1.01 SEMESTRE AUTUNNALE 2026<table>' + header + row1 + '<tr></tr>' + row3 + '<tr></tr></table>'


class SourcesTests(unittest.TestCase):
    def test_supsi_spans_groups_and_period_break(self):
        lessons = parse_supsi(grid(), 'B1.01', '2026-11-02', '2026-11-06', 'SEMESTRE AUTUNNALE 2026')
        self.assertEqual(len(lessons), 3)
        monday = [e for e in lessons if e['date'] == '2026-11-02']
        self.assertEqual([(e['start'], e['end']) for e in monday], [('08:30', '10:15')])
        tuesday = [e for e in lessons if e['date'] == '2026-11-03']
        self.assertEqual(len(tuesday), 2)
        self.assertEqual(tuesday[0]['end'], '09:15')

    def test_nested_table_text_is_not_a_separate_lesson(self):
        lessons = parse_supsi(grid(), 'B1.01', '2026-11-02', '2026-11-02', 'SEMESTRE AUTUNNALE 2026')
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]['title'], 'Course Year 3')

    def test_wrong_room_wrong_semester_and_broken_grid_rejected(self):
        for body, room, term in [(grid(), 'B1.02', 'SEMESTRE AUTUNNALE 2026'),
                                 (grid(), 'B1.01', 'SEMESTRE PRIMAVERILE 2027'),
                                 (grid().replace('colspan="12"', 'colspan="11"', 1),
                                  'B1.01', 'SEMESTRE AUTUNNALE 2026')]:
            with self.subTest(room=room, term=term):
                with self.assertRaises(ValueError):
                    parse_supsi(body, room, '2026-11-02', '2026-11-06', term)

    def test_campus_room_names_are_not_conflated(self):
        self.assertEqual(room_code('a 1 . 04'), 'A1.04')
        self.assertEqual(room_code('A11'), 'A11')
        self.assertEqual(room_locations('A1.03, A1.04'), ['A1.03', 'A1.04'])
        self.assertNotIn('A1.01', room_locations('A11'))

    def test_supsi_inventory_keeps_official_indices(self):
        rooms = supsi_rooms('var rooms = ["D1.01 Aula", "A1.02 Aula", "B1.01 Aula"];')
        self.assertEqual([(index, code) for index, code, _ in rooms], [(2, 'A1.02'), (3, 'B1.01')])

    def test_canonical_programme_slug_links_are_preserved(self):
        page = Page('<a href="https://search.usi.ch/it/offerte-formative/105/master-of-science-in-data-science/piano-orari/61/1">1</a>')
        self.assertIn('/105/master-of-science-in-data-science/', page.links[0])

    def test_combined_supsi_usi_bookings_block_evening_room(self):
        config = {'coverage': {'from': '2026-11-02', 'to': '2026-11-06',
                               'supsi_all_years': True, 'usi_at_supsi': True},
                  'rooms': [{'id': 'B1.01', 'campus': 'Campus Est', 'sector': 'B',
                             'floor': 1, 'is_classroom': True}],
                  'sources': [
                      {'id': 'supsi', 'url': 'https://example.com/supsi', 'format': 'supsi-room',
                       'room': 'B1.01', 'from': '2026-11-02', 'to': '2026-11-06',
                       'term': 'SEMESTRE AUTUNNALE 2026'},
                      {'id': 'usi', 'url': 'https://example.com/usi', 'format': 'usi-ics'}]}
        calendar = ('BEGIN:VCALENDAR\nBEGIN:VEVENT\n'
                    'DTSTART;TZID=Europe/Zurich:20261102T133000\n'
                    'DTEND;TZID=Europe/Zurich:20261102T170000\n'
                    'LOCATION:B1.01\nEND:VEVENT\nEND:VCALENDAR')
        def download(url, previous):
            return {'body': grid() if url.endswith('supsi') else calendar}
        with tempfile.TemporaryDirectory() as directory:
            combined, _ = refresh(config, Path(directory) / 'cache.json', fetcher=download)
        self.assertEqual({e['source'] for e in combined['lessons']}, {'supsi', 'usi'})
        self.assertEqual(search(combined, date(2026, 11, 2), 'evening', time(16, 30), time(22)), [])
        self.assertEqual(search(combined, date(2026, 11, 2), 'day', time(16, 30), time(22)),
                         [('B1.01', time(17), time(22), True)])


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.pages = {}
        directory = []
        for programme_id, name in [('30', 'bachelor-informatics'), ('102', 'bachelor-data-science'),
                                   ('22', 'master-informatics')]:
            url = f'https://search.usi.ch/en/educations/{programme_id}/{name}/schedules'
            directory.append(f'<a href="{url}">{name}</a>')
            self.pages['usi-programme-' + programme_id] = f'<a href="{url}/61/1">Year 1</a>'
            source_id = f'usi-{programme_id}-61-1'
            self.pages[source_id + '-page'] = ('Campus Est A1.03 A1.04 A1.05 '
                                                f'<a href="{url.replace("https:", "webcal:")}/61/1/ics">Calendar</a>')
            self.pages[source_id] = ('BEGIN:VCALENDAR\nX-WR-CALNAME:Test - SA 2026-2027\n'
                'BEGIN:VEVENT\nDTSTART;TZID=Europe/Zurich:20260914T090000\n'
                'DTEND;TZID=Europe/Zurich:20260914T100000\nLOCATION:A1.04\nEND:VEVENT\n'
                'BEGIN:VEVENT\nDTSTART;TZID=Europe/Zurich:20260918T090000\n'
                'DTEND;TZID=Europe/Zurich:20260918T100000\nLOCATION:A1.04\nEND:VEVENT\nEND:VCALENDAR')
        self.pages['usi-directory'] = ''.join(directory)
        self.pages['supsi-directory'] = 'var rooms = ["B1.01 Aula grande"]; <option value="38">14.9.2026</option>'
        self.pages['supsi-title'] = 'SEMESTRE AUTUNNALE 2026'
        self.pages['supsi-footer'] = 'ultimo aggiornamento: 25-09-2026 14:58'
        self.requests = []

    def read(self, source_id, url):
        self.requests.append(source_id)
        return {'body': self.pages[source_id]}

    def test_discovers_every_programme_calendar_and_extra_usi_rooms(self):
        config = discover(self.read)
        self.assertEqual(config['summary']['usi_programmes'], 3)
        self.assertEqual(config['summary']['usi_calendars'], 3)
        self.assertEqual({r['id'] for r in config['rooms']}, {'B1.01', 'A1.03', 'A1.04', 'A1.05'})
        self.assertEqual(len(config['sources']), 4)
        self.assertEqual(config['coverage']['to'], '2026-09-18')
        self.assertEqual(len(self.requests), 13)

    def test_missing_year_is_a_failure_not_a_free_room(self):
        self.pages['usi-programme-102'] = '<p>No published timetable</p>'
        with self.assertRaisesRegex(ValueError, 'no published year links'):
            discover(self.read)

    def test_mismatched_semesters_are_rejected(self):
        self.pages['usi-22-61-1'] = self.pages['usi-22-61-1'].replace('SA 2026', 'SP 2026')
        with self.assertRaisesRegex(ValueError, 'common semester'):
            discover(self.read)

    def test_new_room_requires_inventory_confirmation(self):
        self.pages['usi-22-61-1'] = self.pages['usi-22-61-1'].replace('A1.04', 'B1.99')
        with self.assertRaisesRegex(ValueError, 'New room B1.99'):
            discover(self.read)


if __name__ == '__main__':
    unittest.main()
