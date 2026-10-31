"""Rank feasible room itineraries with a strict entry cutoff and move budget."""
from functools import lru_cache

CUTOFF = 17 * 60


def minutes(value):
    return value.hour * 60 + value.minute


def clock(value):
    return f'{value // 60:02}:{value % 60:02}'


def move_budget(start, end, *, afternoon=2, preferred=3, maximum=4):
    full_day = start < 12 * 60 and end >= 16 * 60 and end - start >= 6 * 60
    return (maximum, preferred, 'Full day') if full_day else (afternoon, afternoon, 'Afternoon / short session')


def plan_session(slots, start, end, *, max_moves=2, wait=0, transfer=2, limit=5, min_study=30, priority='fewer_moves'):
    """Find routes using a DAG of intervals with strictly increasing end times.

    Earliest feasible entry drives the search; the final itinerary shifts moves
    later, retaining a useful study block in every room. Transfer time is a break
    in studying, never represented as time inside a free room.
    """
    if end <= start or not 0 <= max_moves <= 4 or transfer < 0 or wait < 0 or min_study < 1:
        raise ValueError('Invalid study planning limits.')
    if priority not in ('fewer_moves', 'more_study'):
        raise ValueError('Invalid planning priority.')
    minimum = min_study
    intervals = sorted(set((room, max(start, minutes(a) + bool(a.second or a.microsecond)), min(end, minutes(b)))
                           for room, a, b, _ in slots if minutes(b) > start and minutes(a) < end))

    def key(path):
        sectors = sum(intervals[a][0][0] != intervals[b][0][0] for a, b in zip(path, path[1:]))
        return len(path), sectors, tuple(intervals[i][0] for i in path)

    @lru_cache(maxsize=None)
    def routes(index, entered, remaining):
        room, left, right = intervals[index]
        if right >= end:
            return ((index,),) if end - entered >= minimum else ()
        if not remaining:
            return ()
        candidates = []
        for nxt, (other, a, b) in enumerate(intervals):
            if other == room or b <= right:
                continue
            departure = max(entered + minimum, a - transfer)
            arrival = departure + transfer
            if departure > right or arrival >= b or arrival >= CUTOFF:
                continue
            for tail in routes(nxt, arrival, remaining - 1):
                candidates.append((index, *tail))
        return tuple(sorted(set(candidates), key=key)[:limit])

    candidates = []
    for index, (_, left, right) in enumerate(intervals):
        entered = max(start, left)
        if entered - start <= wait and entered < right and entered < CUTOFF:
            for path in routes(index, entered, max_moves):
                # Schedule backwards to stay in each preceding room as long as possible.
                entries = [entered] * len(path)
                leaves = [end] * len(path)
                valid = True
                for j in range(len(path) - 1, 0, -1):
                    prev = intervals[path[j - 1]]
                    current = intervals[path[j]]
                    entries[j] = min(prev[2] + transfer, CUTOFF - 1, leaves[j] - minimum)
                    leaves[j - 1] = entries[j] - transfer
                    if entries[j] < current[1]:
                        valid = False
                if not valid or leaves[0] - entered < minimum:
                    continue
                segments = [(intervals[i][0], entries[j], leaves[j]) for j, i in enumerate(path)]
                if any(b - a < minimum for _, a, b in segments):
                    continue
                candidates.append({'segments': segments, 'wait': entered - start,
                                   'moves': len(path) - 1, 'transfer': transfer,
                                   'study_minutes': sum(b - a for _, a, b in segments)})
    def ranking(plan):
        segments = plan['segments']
        objective = (plan['moves'], plan['wait']) if priority == 'fewer_moves' else (-plan['study_minutes'], plan['moves'], plan['wait'])
        return (*objective, -min(b - a for _, a, b in segments),
                sum(a[0][0] != b[0][0] for a, b in zip(segments, segments[1:])),
                tuple(s[0] for s in segments))
    unique = {tuple(p['segments']): p for p in candidates}
    return sorted(unique.values(), key=ranking)[:limit]


def useful_slots(slots, start, end, *, mode='day', min_study=30):
    """Rank usable study blocks; prefer a full-session room to partial options."""
    minimum = min_study
    useful = [s for s in slots if s[3] and minutes(s[2]) - minutes(s[1]) >= minimum]
    whole = [s for s in useful if minutes(s[1]) == start and minutes(s[2]) == end]
    if whole and mode != 'day':
        return sorted(whole, key=lambda s: s[0])
    return sorted(useful, key=lambda s: (-(minutes(s[2]) - minutes(s[1])), minutes(s[1]), s[0]))


def opening_soon(slots, start, *, within=15, min_study=30):
    options = [s for s in slots if start < minutes(s[1]) <= start + within and minutes(s[1]) < CUTOFF
               and minutes(s[2]) - minutes(s[1]) >= min_study]
    return sorted(options, key=lambda s: (-minutes(s[2]), minutes(s[1]), s[0]))[:5]
