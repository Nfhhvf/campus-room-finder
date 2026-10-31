# Campus Est classroom finder

Find a classroom to study in at Campus Est, directly from your terminal.
The program combines SUPSI and USI lessons to find gaps on **floor 1, sectors
A and B**, with saved timetables and automatic update checks at every launch.

It helps answer: **“Which room can I enter before 17:30 and use for my study
session without a scheduled lesson interrupting me?”** The 17:30 badge-entry rule
comes from the project's intended use; it is not independently verified.

This is an independent student project, unaffiliated with SUPSI or USI. It searches
published timetables and does not reserve classrooms.

## Features

- Combine SUPSI DTI room schedules with USI Bachelor/Master calendars.
- Discover programme/year links automatically at every online launch.
- Search a whole study session, availability at arrival, or all daily gaps.
- Keep saved lessons and check source files for updates.
- Use an explicit offline mode when you cannot connect.
- Keep the last successful snapshot if a download or import fails.
- Run from the terminal with no graphical interface or account configuration.

## Requirements

- Python **3.11 or newer** and Git to clone the repository.
- Internet access for the first live import and subsequent online checks.
- The `Europe/Zurich` timezone database (normally included on Linux/macOS).

There are no third-party Python dependencies on systems with timezone data.
On Windows, or if Python reports `ZoneInfoNotFoundError`, install the timezone
database with `python -m pip install tzdata`. Use `python` or `py` in place of
`python3` below if that is how Python is installed on your computer.

## Run

```sh
git clone https://github.com/Nfhhvf/Cross-reference-time-tables-.git
cd Cross-reference-time-tables-
python3 install.py
python3 rooms.py
```

Run `install.py` once to download, import and save the current timetables. It
prints a ready message after a successful import. Re-running it safely checks
for updates without deleting saved data. This is a data setup step; it does not
install system packages, change your PATH or require administrator access.

After setup, just run `python3 rooms.py` from the project folder. Every launch
checks for timetable changes and reuses saved lessons. If you skip setup, the
first normal launch also performs the initial download automatically.

For a quick trial without downloading any timetables:

```sh
python3 rooms.py --demo
```

Example fictional output:

```text
DEMO: fictional rooms and lessons. Do not use these results to choose a room.
DEMO-B-1         16:30–22:00  entry before cutoff
```

Each launch discovers and checks the current SUPSI and USI timetables, then asks
for a search mode, date, arrival time and study end time. The first refresh can
take a few minutes because it checks all published programme/year pages and
calendars. Subsequent launches also check every source, using HTTP cache
validators where supported. Known sources are checked in parallel and unchanged
lessons are reused without re-parsing. Network/server speed still affects startup;
offline mode is available when you explicitly want to skip checks. All
user-facing times use Europe/Zurich.

Modes:

1. **Entire session:** classrooms with no published lesson throughout your session;
   arrival must be strictly before 17:30.
2. **Free at arrival:** classrooms without a lesson at your arrival, showing how
   long the gap lasts, limited to your requested end time.
3. **Daily gaps:** every timetable gap inside your chosen time window.

The 17:30 cutoff follows your stated badge-entry rule. Later gaps are marked as
unavailable for entry. The requested end time is not a verified building closing
time or permission to stay overnight.

Without prompts:

These examples use the autumn 2026 teaching window. For other semesters, choose
a date within the supported range printed by the program.

```sh
python3 rooms.py --mode evening --date 2026-11-02 --start 16:30 --end 22:00
python3 rooms.py --mode now --date 2026-11-02 --start 16:30 --end 22:00
python3 rooms.py --mode day --date 2026-11-02 --start 08:30 --end 20:45
```

## Where the data comes from

- [SUPSI DTI Untis](https://www3.supsi.ch/inside/area_riservata_dti/orari/definitivi/):
  discovers the first-floor A/B room directory and reads each room timetable.
  Room timetables combine the classes from all years in this DTI export, avoiding
  separate per-class scraping. This does not establish coverage of other
  departments or unpublished bookings.
- [USI Informatics directory](https://www.inf.usi.ch/it/informazioni-pratiche/orari):
  follows every linked Bachelor/Master programme, every published semester/year
  page, and its calendar subscription. This includes Informatics, Data Science,
  and the other listed Masters so their bookings are included too. Doctoral
  programmes are outside the requested Bachelor/Master scope.
- USI room guides identify A1.03, A1.04 and A1.05 as Campus Est teaching rooms;
  these extend the SUPSI directory. A11 and A21 are Campus Ovest and must never
  be converted into first-floor Campus Est room IDs.

**SUPSI publishes a recurring weekly pattern, not dated exceptions.** It is
expanded within the dated USI teaching window for the common published semester.
The result is a candidate timetable gap, not a confirmed room reservation or
proof of physical access. SUPSI holiday cancellations and ad hoc changes absent
from the public export cannot be inferred. Results display this limitation and
the publication time reported by SUPSI separately from the latest download time.
Dates outside the supported teaching window are rejected.

Rooms marked `is_classroom` are teaching rooms included in the search, not an
assertion that the institution permits unsupervised study there. Door access,
room-specific restrictions and unlisted reservations remain unverified. A newly
observed first-floor A/B room not in the known inventory stops discovery for
review rather than silently omitting its bookings.

## Saved lessons and update checks

`settings.json` enables live discovery by default. Original source text, HTTP
validators, imported lessons and the latest successful check time are stored in
`.cache/timetables.json`. ETag and Last-Modified checks avoid downloading unchanged
sources when the server supports them; otherwise the program compares hashes.
Parsed source lessons are also cached and checked for corruption before reuse.
Calendar generation timestamps alone do not trigger another lesson import.

On later launches, a bounded pool of six downloads checks previously known source
URLs together while discovery verifies the current programme/year membership.
Removed sources do not block the new semester merely because an old URL stopped
working. Required-source failures still stop the refresh. Discovery continues to
follow new links and does not rely on a permanently fixed list.

Every complete refresh rebuilds the lesson list, including deletions, moves and
cancelled USI events. The cache is replaced atomically after every required
source has downloaded and imported successfully. A network, discovery or parsing
failure leaves the previous snapshot unchanged and stops the online search.

Explicitly use previously saved lessons without a network check:

```sh
python3 rooms.py --offline
```

Offline results show a warning and the last successful check time. There is no
silent fallback to stale data. Refreshes only detect updates published when the
program starts; changes published later are detected on the next launch.

The program follows the current official directory on each online launch, so new
programme/year links are discovered automatically. A programme with no published
year links, missing calendar, incompatible semester, malformed timetable or
unrecognized calendar recurrence stops the refresh. It does not label missing
data as an available room. The supported SUPSI and USI semesters must overlap.

## Other data and tests

```sh
python3 rooms.py --demo
python3 -m unittest discover -s tests -v
```

The demo is fictional and never accesses the network. A manually prepared
schedule can be searched with `--data schedule.json` (labelled as not checked
online); `examples/demo.json` shows its schema.

`--config path.json` allows a custom explicit source list instead of discovery.
`examples/timetable-sources.json` is deliberately incomplete and cannot produce
room results. Custom sources support `usi-ics`, `supsi-room`, and `lesson-json`;
optional `room_aliases` maps verified alternate names. Recurring ICS rules and
overnight events currently require an importer update and are rejected.

Use `--cache path.json` to select a separate cache. Cache and local configuration
files are ignored by Git. The default cache and settings paths are relative to
the program, so you can also run it by absolute path from another directory.

Network access requires www3.supsi.ch, www.inf.usi.ch and search.usi.ch. In this
managed cloud, network commands need the supported sandbox network permission;
normal local terminals use their existing internet connection and TLS trust.

## Project structure

```text
rooms.py                 Interactive menu, command-line options and gap search
install.py               First-time timetable download and cache preparation
timetable_sources.py     USI discovery, room matching and SUPSI grid parser
timetable_cache.py       Downloads, calendar import and atomic saved snapshots
settings.json            Default live-discovery configuration
examples/                Fictional demo and incomplete custom-source example
tests/                   Offline regression tests
.github/workflows/       Automated tests for pushes and pull requests
```

## Troubleshooting

| Message or situation | What to do |
| --- | --- |
| First launch takes a few minutes | Wait for the printed discovery/import stages to complete; all required sources are checked. |
| Download fails or returns HTTP 403 | Check the network and domain permissions. A proxy rejection does not establish that SUPSI/USI requires a login. |
| No saved lessons available offline | Complete one successful online launch first. Caches are not included in the GitHub repository. |
| Date outside timetable coverage | Choose a date within the printed supported range. Refresh online when a new semester is published. |
| Missing programme, changed page format or incompatible semester | The search stops to avoid using incomplete data. Open an issue with the error and source URL. |
| No rooms found for an evening arrival at/after 17:30 | Choose an arrival before the configured badge-entry cutoff. |
| `ZoneInfoNotFoundError` | Install `tzdata` as described above. |

To get future code updates, run `git pull` from the project folder. Timetable
updates are checked automatically by normal launches and do not require a Git pull.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and reporting problems,
and [CHANGELOG.md](CHANGELOG.md) for the initial feature list.

## Planned terminal interface

The current interface uses simple numbered prompts. Future interface work will
focus on consistent menus, clearer loading feedback and readable result tables.
Those presentation changes will build on the same import, cache and search logic.
