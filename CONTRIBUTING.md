# Contributing

## Development

Use Python 3.11+ with the Europe/Zurich timezone database. The code uses the
standard library; there are no build steps or application services to start.

```sh
python3 -m unittest discover -s tests -v
python3 rooms.py --demo --mode evening --date 2026-10-31 --start 16:30 --end 22:00
```

Tests run without network access. They cover interval merging, room-code matching,
SUPSI table spans, USI calendar discovery/import, incomplete source coverage,
cancellations, conditional requests, offline recovery and atomic refresh failures.
GitHub Actions runs these checks on pushes and pull requests with Python
3.11, 3.12 and 3.13. Live timetable imports are tested manually to avoid placing
repeated automated requests on university servers.

For a live check:

```sh
python3 rooms.py
```

Choose a date from the supported range printed after import. Check a known
scheduled lesson against the official source and verify the room is excluded
while that lesson is running. Test offline mode only after a successful import.

## Changes to source adapters

- Keep TLS verification and the configured network proxy intact.
- Treat a missing programme/year or malformed source as incomplete coverage.
- Preserve the last successful cache if any required source fails.
- Keep room IDs campus-specific: A11 is not A1.01.
- Add offline fixtures/tests for new page structures and calendar properties.
- Document any inferred dates or recurring patterns; do not call inferred gaps
  confirmed room reservations or confirmed physical access.
- Limit concurrent downloads and use server cache validators when available.

Use `python3 install.py --cache path/to/new-cache.json` to test first-time setup
without modifying your normal cache. Run it again with the same path to measure
a subsequent refresh. A normal search checks for updates even after setup.

If source parsing semantics change, bump `parser_version` in `cached_lessons`
so saved parsed lessons are rebuilt. Keep tests showing that timestamp-only
calendar changes reuse lessons while real date/time/room changes invalidate them.

The default live configuration is `settings.json`. A custom explicit source list
can be passed with `--config path.json`; an incomplete example is included under
`examples/`. Local cache files and personal configuration stay out of Git.

## Reporting a problem

Open an issue in this repository with:

1. The command you ran, your Python version and operating system.
2. The date, time, room and expected result.
3. The full error message and the relevant public timetable URL.
4. Whether the run was online, offline, a demo or a manual local schedule.

Do not include credentials, badge information, personal calendar exports or
private timetable data. A small public-source excerpt is usually enough to
reproduce a parsing problem.
