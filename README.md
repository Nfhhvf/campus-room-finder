# Campus Est Rooms

Find classrooms with no scheduled lessons at Campus Est, floor 1, sector B.
Runs in the terminal and combines SUPSI and USI timetables.

## Setup

Requires Python 3.11+.

```sh
git clone https://github.com/Nfhhvf/campus-room-finder.git
cd campus-room-finder
python3 install.py
```

Setup downloads the timetables and installs the `roomfinder` command for your
user. Open a new terminal after setup. Keep the project folder in place.
On systems without timezone data,
install it with `python3 -m pip install tzdata`.

On macOS, if setup reports `CERTIFICATE_VERIFY_FAILED`, open your Python folder
under Applications and run **Install Certificates.command**, then retry setup.
This applies to Python installed from python.org.

## Use

```sh
roomfinder
```

1. **Plan a session:** uses today's date and current time, then asks when you want
   to start and finish. Recommends a room for the session or a connected room-change plan.
2. **Arrive and study:** confirms today or another date, asks your arrival and end
   time, and compares starting immediately with a short wait (15 minutes by default).
3. **Daily overview:** confirms the date and recommends useful study periods.
4. **Settings:** change your preferences; every change is saved locally.

Recommendations favour a room covering the whole session, then practical routes
with fewer moves or a short wait. Gaps and stops under 30 minutes are excluded
unless you explicitly request a shorter session. The best option appears first;
choose whether to see alternatives. Today's daily overview starts from the current time.

Use the numbered menu and press Enter to accept a default. Dates also accept
**DD-MM-YY**, `today` and `tomorrow`; type `b` to return to the menu or `q` to quit.
You can run another search without reloading the timetables.
You can also type a date directly at the "Today?" prompt.

Plans prefer fewer moves: at most two for an afternoon/short session. A full day
(starting before noon, lasting at least six hours and ending at/after 16:00)
prefers up to three changes; four is a fallback. Moves allow two minutes by default.
Adjust these in Settings. Every new room must still be entered before 17:00.

First setup asks your usual study end time, minimum stay, maximum wait and move
time. Settings also controls room-change limits, fewer-moves vs more-study-time
ranking, result display, animation and
colors. Preferences live in `~/.config/campus-room-finder/preferences.json` and
survive program updates. Use Restore defaults to reset them. You can open Settings
without loading timetables with `roomfinder --settings`.

Each launch checks GitHub for a newer program version, updates it and restarts
before refreshing the timetables. Local changes are preserved; automatic code
updates only run on a clean `main` branch. If GitHub is unreachable, the installed
version still opens. Use `--no-update` to skip only the code check.

To use saved timetables without any update checks:

```sh
roomfinder --offline
```

Try fictional data with `roomfinder --demo`. Run `roomfinder --help`
for all options. Demo and help commands do not check GitHub.

Already set up? Run `python3 install.py --command-only` once to add the command
without downloading the timetables again. On macOS/Linux it lives in
`~/.local/bin`; setup adds that directory to your zsh/bash startup file if needed.
Running `python3 rooms.py` directly also works.

## Data

Sources: [SUPSI DTI](https://www3.supsi.ch/inside/area_riservata_dti/orari/definitivi/)
and [USI Informatics](https://www.inf.usi.ch/it/informazioni-pratiche/orari).

SUPSI publishes a weekly pattern; USI provides dated lessons. Searches stay
within the supported semester. Unlisted bookings and door access aren't covered.

Maintained by [Nfhhvf](https://github.com/Nfhhvf).
