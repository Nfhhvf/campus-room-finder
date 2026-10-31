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


def plan_session(slots, start, end, *, max_moves=2, wait=0, transfer=2, limit=5, min_study=30, priority='fewer_moves', favorites=()):
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
    favorites = set(favorites)
    intervals = sorted(set((room, max(start, minutes(a) + bool(a.second or a.microsecond)), min(end, minutes(b)))
                           for room, a, b, _ in slots if minutes(b) > start and minutes(a) < end))

    def key(path):
        sectors = sum(intervals[a][0][0] != intervals[b][0][0] for a, b in zip(path, path[1:]))
        return len(path), sum(intervals[i][0] not in favorites for i in path), sectors, tuple(intervals[i][0] for i in path)

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
        return (*objective, -sum(b - a for room, a, b in segments if room in favorites), -min(b - a for _, a, b in segments),
                sum(a[0][0] != b[0][0] for a, b in zip(segments, segments[1:])),
                tuple(s[0] for s in segments))
    unique = {tuple(p['segments']): p for p in candidates}
    return sorted(unique.values(), key=ranking)[:limit]


def useful_slots(slots, start, end, *, mode='day', min_study=30, favorites=()):
    """Rank usable study blocks; prefer a full-session room to partial options."""
    minimum = min_study
    useful = [s for s in slots if s[3] and minutes(s[2]) - minutes(s[1]) >= minimum]
    whole = [s for s in useful if minutes(s[1]) == start and minutes(s[2]) == end]
    if whole and mode != 'day':
        return sorted(whole, key=lambda s: (s[0] not in favorites, s[0]))
    return sorted(useful, key=lambda s: (-(minutes(s[2]) - minutes(s[1])), minutes(s[1]), s[0] not in favorites, s[0]))


def recommend(slots, start, end, prefs, *, mode='evening', minimum=None, transfer=None, budget=None, preferred=None):
    minimum = prefs['min_study'] if minimum is None else minimum
    transfer = prefs['move_minutes'] if transfer is None else transfer
    default_budget, default_preferred, kind = move_budget(start, end, afternoon=prefs['afternoon_moves'],
                                                         preferred=prefs['full_day_preferred'], maximum=prefs['full_day_max'])
    budget = default_budget if budget is None else budget
    preferred = min(default_preferred if preferred is None else preferred, budget)
    useful = useful_slots(slots, start, end, min_study=minimum, favorites=prefs.get('favorites', []))
    whole = [row for row in useful if minutes(row[1]) == start and minutes(row[2]) == end]
    def single(row):
        room, a, b, _ = row
        left, right = minutes(a), minutes(b)
        return {'segments': [(room, left, right)], 'wait': left - start, 'moves': 0,
                'transfer': transfer, 'study_minutes': right - left, 'complete': left == start and right == end}
    options = [single(row) for row in whole]
    if not options:
        kwargs = {'wait': prefs['max_wait'], 'transfer': transfer, 'min_study': minimum,
                  'priority': prefs['priority'], 'favorites': prefs.get('favorites', [])}
        options = plan_session(slots, start, end, max_moves=preferred, **kwargs)
        if not options and budget > preferred:
            options = plan_session(slots, start, end, max_moves=budget, **kwargs)
        for plan in options:
            plan['complete'] = plan['wait'] == 0
    if not options:
        partials = useful if mode == 'day' else [r for r in useful if minutes(r[1]) - start <= prefs['max_wait']]
        options = [single(row) for row in partials]
    return {'options': options, 'useful': useful, 'whole': whole, 'budget': budget,
            'preferred': preferred, 'kind': kind, 'minimum': minimum, 'transfer': transfer}


def opening_soon(slots, start, *, within=15, min_study=30):
    options = [s for s in slots if start < minutes(s[1]) <= start + within and minutes(s[1]) < CUTOFF
               and minutes(s[2]) - minutes(s[1]) >= min_study]
    return sorted(options, key=lambda s: (-minutes(s[2]), minutes(s[1]), s[0]))[:5]
