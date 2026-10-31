import contextlib
import io
import os
import sys
import unittest
from datetime import date, time
from unittest.mock import patch

import rooms
from terminal_ui import Progress, QuitSearch, choose_day, choose_mode, choose_time, show_results


class TerminalTests(unittest.TestCase):
    def test_invalid_menu_choice_can_be_retried(self):
        with patch('builtins.input', side_effect=['oops', '2']), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(choose_mode(), 'now')
        self.assertIn('Choose 1, 2, 3 or q', out.getvalue())

    def test_quit_at_prompt(self):
        with patch('builtins.input', return_value='q'), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(QuitSearch):
                choose_mode()

    def test_date_keywords_and_coverage_retry(self):
        coverage = {'from': '2026-10-01', 'to': '2026-10-31'}
        with patch('builtins.input', side_effect=['2027-01-01', 'tomorrow']), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(choose_day(date(2026, 10, 30), date(2026, 10, 30), coverage), date(2026, 10, 31))

    def test_invalid_and_earlier_end_times_retry(self):
        with patch('builtins.input', side_effect=['25:00', '15:00', '19:30']), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(choose_time('Until', '22:00', after=time(16, 30)), time(19, 30))

    def test_results_show_duration_and_late_entry_without_escape_codes(self):
        results = [('B1.01', time(16), time(18), True), ('B1.02', time(19), time(22), False)]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            show_results(results, date(2026, 10, 31), time(16), time(22), 'day')
        text = out.getvalue()
        for expected in ('2h 00m', 'Unavailable', '2 rooms / 2 gaps', 'Until'):
            self.assertIn(expected, text)
        self.assertNotIn('\033', text)

    def test_small_terminal_uses_compact_table(self):
        with patch('terminal_ui.shutil.get_terminal_size', return_value=os.terminal_size((48, 24))), contextlib.redirect_stdout(io.StringIO()) as out:
            show_results([('B1.01', time(16), time(22), True)], date(2026, 10, 31), time(16), time(22), 'day')
        self.assertIn('Free from - until', out.getvalue())
        self.assertNotIn('Free for', out.getvalue())

    def test_progress_failure_stops_cleanly_in_plain_output(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(ValueError):
                with Progress('Updating') as progress:
                    progress.update('Reading calendars')
                    raise ValueError('network problem')
        self.assertIn('!  Updating', out.getvalue())
        self.assertNotIn('\033', out.getvalue())

    def test_interactive_repeat_search_without_reloading(self):
        answers = ['1', '2026-10-31', '16:30', '22:00', 'y',
                   '3', '2026-10-31', '16:30', '22:00', 'n']
        with patch.object(sys, 'argv', ['rooms.py', '--demo']), \
                patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', side_effect=answers), \
                patch('rooms.refresh', side_effect=AssertionError('Demo accessed network')), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rooms.main(), 0)
        self.assertIn('Free for your whole session', out.getvalue())
        self.assertIn('Free periods', out.getvalue())

    def test_invalid_cli_range_returns_failure(self):
        with patch.object(sys, 'argv', ['rooms.py', '--demo', '--mode', 'day', '--date', '2026-10-31',
                                       '--start', '20:00', '--end', '19:00']), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rooms.main(), 1)
        self.assertIn('Study end must be later', out.getvalue())

    def test_ctrl_c_exits_without_traceback(self):
        with patch.object(sys, 'argv', ['rooms.py', '--demo']), \
                patch('builtins.input', side_effect=KeyboardInterrupt), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rooms.main(), 0)
        self.assertIn('Closed.', out.getvalue())


if __name__ == '__main__':
    unittest.main()
