"""Verify the published October flow against its event log, without private scripts.

Read-only: validates recorded status residence, not unrecorded working time.
The active S-11 is deliberately excluded from the completed October cohort.
"""
import csv
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with (ROOT / path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def unique(data):
    keyed = {r['item_id']: r for r in data}
    if len(keyed) != len(data):
        raise ValueError('Duplicate item_id')
    return keyed


def verify():
    events = {}
    for line in (ROOT / 'lr04_kanban/events.md').read_text(encoding='utf-8').splitlines():
        cells = [cell.strip() for cell in line.split('|')]
        if len(cells) >= 6 and cells[2].startswith('F-'):
            events.setdefault(cells[2], []).append((cells[1], cells[3]))
    flow = unique(rows('lr14_metrics/flow.csv'))
    timed = unique(rows('lr04_kanban/flow_timestamps.csv'))
    expected = {f'F-{n:03}' for n in range(1, 19)}
    if set(timed) != expected or not expected <= flow.keys():
        raise ValueError('October cohort must contain F-001 through F-018')
    seconds = []
    for key, r in timed.items():
        ev = events.get(key, [])
        starts = [t for t, action in ev if action.startswith('Ready → In progress')]
        ends = [t for t, action in ev if action.endswith('→ Done')]
        if len(starts) != 1 or len(ends) != 1:
            raise ValueError(f'{key}: expected one start and one Done transition')
        start, end = starts[0], ends[0]
        if r['source_file'] != 'lr04_kanban/events.md' or r['done_utc'] != end:
            raise ValueError(f'{key}: timestamp/source mismatch')
        for field, recorded in [('start_date', start[:10]), ('done_date', end[:10])]:
            # These October events are away from the UTC/local midnight boundary.
            if r[field] != recorded or flow[key][field] != recorded:
                raise ValueError(f'{key}: date differs from event log')
        if date.fromisoformat(flow[key]['created_date']) > date.fromisoformat(r['start_date']):
            raise ValueError(f'{key}: start before creation')
        if len(start) == 10:
            if r['precision'] != 'start_day_only' or r['start_utc'] or r['elapsed_seconds']:
                raise ValueError(f'{key}: unknown start time must stay unknown')
        else:
            elapsed = int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
            if elapsed < 0 or r['precision'] != 'second' or r['start_utc'] != start or int(r['elapsed_seconds']) != elapsed:
                raise ValueError(f'{key}: elapsed time differs from recorded transitions')
            seconds.append(elapsed)
    return len(timed), seconds


if __name__ == '__main__':
    count, seconds = verify()
    print(f'PASS: {count} completed October cards; {len(seconds)} exact intervals; '
          'F-001 start has day precision only. No data changed.')
