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

## Use

```sh
python3 rooms.py
```

Choose a date, arrival time and study end time. Find a room free for the whole
session, see which rooms are free at arrival, or list the day's free periods.
Evening searches require arrival before 17:30.

Use the numbered menu and press Enter to accept a default. Dates also accept
`today` and `tomorrow`; type `q` to quit. Results show free periods, duration and
the entry cutoff. You can run another search without reloading the timetables.

Timetables are checked for updates at every launch. To use saved data without
checking for changes:

```sh
python3 rooms.py --offline
```

Try fictional data with `python3 rooms.py --demo`. Run `python3 rooms.py --help`
for all options.

## Data

Sources: [SUPSI DTI](https://www3.supsi.ch/inside/area_riservata_dti/orari/definitivi/)
and [USI Informatics](https://www.inf.usi.ch/it/informazioni-pratiche/orari).

SUPSI publishes a weekly pattern; USI provides dated lessons. Searches stay
within the supported semester. Unlisted bookings and door access aren't covered.

Maintained by [Nfhhvf](https://github.com/Nfhhvf).
