import unittest
from datetime import date, time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rooms import free_slots, load_schedule, search


class AvailabilityTests(unittest.TestCase):
    def test_overlapping_lessons_and_boundaries(self):
        lessons = [dict(start='15:00', end='17:00'), dict(start='16:00', end='18:00'),
                   dict(start='18:00', end='19:00')]
        self.assertEqual(list(free_slots(lessons, time(16), time(22))), [(time(19), time(22))])

    def test_realistic_modes_and_cutoff(self):
        data = load_schedule(Path(__file__).resolve().parents[1] / 'examples/demo.json', date(2026, 10, 31))
        day = date(2026, 10, 31)
        self.assertEqual(len(search(data, day, 'now', time(16, 30), time(22))), 2)
        self.assertEqual([r[0] for r in search(data, day, 'evening', time(16, 30), time(22))], ['DEMO-B-1'])
        self.assertEqual(search(data, day, 'evening', time(17, 30), time(22)), [])

    def test_outside_coverage_rejected(self):
        with self.assertRaises(ValueError):
            load_schedule(Path(__file__).resolve().parents[1] / 'examples/demo.json', date(2027, 1, 1))


if __name__ == '__main__':
    unittest.main()
