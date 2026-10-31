# Campus Est Rooms

Find classrooms with no scheduled lessons at Campus Est, floor 1, sectors A and B.
Runs in the terminal and combines SUPSI and USI timetables.

## Setup

Requires Python 3.11+.

```sh
git clone https://github.com/Nfhhvf/Cross-reference-time-tables-.git
cd Cross-reference-time-tables-
python3 install.py
```

Setup downloads and saves the timetables. On systems without timezone data,
install it with `python3 -m pip install tzdata`.

On macOS, if setup reports `CERTIFICATE_VERIFY_FAILED`, open your Python folder
under Applications and run **Install Certificates.command**, then retry setup.
This applies to Python installed from python.org.

## Use

```sh
python3 rooms.py
```

1. **Plan a session:** uses today's date and current time, then asks when you want
   to start and finish. Shows all rooms covering the session, or ranked room-change
   plans if none can cover it alone.
2. **Arrive and study:** confirms today or another date, asks your arrival and end
   time, and compares starting immediately with waiting up to 15 minutes.
3. **Daily overview:** confirms the date and lists gaps from 08:30 to 22:00.

Use the numbered menu and press Enter to accept a default. Dates also accept
**DD-MM-YY**, `today` and `tomorrow`; type `q` to quit. You can run another search
without reloading the timetables.

Plans prefer fewer moves: at most two for an afternoon/short session. A full day
(starting before noon, lasting at least six hours and ending at/after 16:00)
prefers up to three changes; four is a fallback. Each move allows two minutes,
shown as a break. Every new room must be entered before 17:30. Use `--max-moves`
or `--move-minutes` to adjust those limits.

Each launch checks GitHub for a newer program version, updates it and restarts
before refreshing the timetables. Local changes are preserved; automatic code
updates only run on a clean `main` branch. If GitHub is unreachable, the installed
version still opens. Use `--no-update` to skip only the code check.

To use saved timetables without any update checks:

```sh
python3 rooms.py --offline
```

Try fictional data with `python3 rooms.py --demo`. Run `python3 rooms.py --help`
for all options. Demo and help commands do not check GitHub.

## Data

Sources: [SUPSI DTI](https://www3.supsi.ch/inside/area_riservata_dti/orari/definitivi/)
and [USI Informatics](https://www.inf.usi.ch/it/informazioni-pratiche/orari).

SUPSI publishes a weekly pattern; USI provides dated lessons. Searches stay
within the supported semester. Unlisted bookings and door access aren't covered.

Maintained by [Nfhhvf](https://github.com/Nfhhvf).
