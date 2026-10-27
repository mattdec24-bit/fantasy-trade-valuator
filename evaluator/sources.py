"""Only fixed-host ESPN GET requests. No write-capable ESPN client is used."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request
from .network import urlopen

from .model import League, Player, Team, from_dict, SLOT_POSITIONS, finite

ROOT = Path(__file__).resolve().parent.parent
SLOTS = {0: 'QB', 2: 'RB', 3: 'RB/WR', 4: 'WR', 5: 'WR/TE', 6: 'TE', 7: 'OP', 16: 'D/ST', 17: 'K', 23: 'RB/WR/TE'}
POS = {1: 'QB', 2: 'RB', 3: 'WR', 4: 'TE', 5: 'K', 16: 'D/ST'}


def demo():
    return from_dict(json.loads((ROOT / 'fixtures/demo.json').read_text()))


def espn_get(year, league_id, views, cookie, fantasy_filter=None):
    # IDs are runtime-only, never embedded in tracked configuration or logs.
    if not str(year).isdigit() or not str(league_id).isdigit():
        raise ValueError('ESPN year and league ID must be numeric runtime configuration')
    url = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}?' + '&'.join('view=' + v for v in views)
    headers = {'Accept': 'application/json'}
    if cookie:
        if '\r' in cookie or '\n' in cookie:
            raise ValueError('Invalid credential format')
        headers['Cookie'] = cookie
    if fantasy_filter:
        headers['X-Fantasy-Filter'] = json.dumps(fantasy_filter)
    try:
        with urlopen(Request(url, headers=headers, method='GET'), timeout=15) as response:
            if response.geturl().split('?')[0] != url.split('?')[0]:
                raise ValueError('Unexpected ESPN redirect')
            body = response.read(8_000_001)
        if len(body) > 8_000_000:
            raise ValueError('ESPN response too large')
        return json.loads(body)
    except (URLError, ValueError, OSError):
        raise ValueError('ESPN read failed; check local configuration and access. No credentials are logged.') from None


def normalize_espn(data, free_data, year):
    week = int(data.get('scoringPeriodId', 1))
    counts = data['settings']['rosterSettings']['lineupSlotCounts']
    unknown = [k for k, v in counts.items() if int(v) and int(k) not in set(SLOTS) | {20,21,24}]
    if unknown:
        raise ValueError('This league has unsupported lineup slots')
    slots = tuple(SLOTS[int(k)] for k, n in sorted(counts.items(), key=lambda kv: int(kv[0]))
                  if int(k) in SLOTS for _ in range(int(n)))
    limit = sum(int(v) for k, v in counts.items() if int(k) not in {21,24})
    def parse(raw):
        p = raw.get('playerPoolEntry', {}).get('player', raw.get('player', raw))
        projections = {}
        for stat in p.get('stats', []):
            if stat.get('seasonId') != int(year) or stat.get('statSourceId') != 1:
                continue
            mode = ('week' if stat.get('statSplitTypeId') == 1 and stat.get('scoringPeriodId') == week
                    else 'season' if stat.get('statSplitTypeId') == 0 else None)
            if mode is None:
                continue
            value = stat.get('appliedTotal')
            finite(value)  # Validate every matching record, even one followed by a valid duplicate.
            value = float(value) if value is not None else None
            # Compare before Player's display rounding so small conflicts are not hidden.
            if mode in projections and projections[mode] != value:
                raise ValueError(f'Conflicting ESPN {mode} projection records; snapshot rejected')
            projections[mode] = value
        position = POS.get(p.get('defaultPositionId'))
        if position is None:
            raise ValueError('Unsupported ESPN player position')
        # A current-week projection is unavailable when ESPN does not supply one.
        return Player(str(p['id']), p['fullName'], position, str(p.get('proTeamId', '')),
                      projections.get('week'), projections.get('season'),
                      p.get('injuryStatus', 'ACTIVE'), False, False,
                      tuple(SLOTS[s] for s in p.get('eligibleSlots', []) if s in SLOTS))
    teams = []
    for team in data.get('teams', []):
        entries = team.get('roster', {}).get('entries', [])
        if any(e.get('lineupSlotId') in {21,24} for e in entries):
            raise ValueError('Occupied IR slots require explicit roster handling; this version does not assume IR moves')
        teams.append(Team(str(team['id']), team.get('name') or f"{team.get('location', '')} {team.get('nickname', '')}".strip(), tuple(parse(e) for e in entries)))
    if len(teams) < 2:
        raise ValueError('ESPN did not return at least two rosters')
    # Player weekly availability is not reliably present in roster responses.
    # Do not pretend these are live remaining-week forecasts; adapter marks it in source.
    return League(data['settings']['name'], week, int(year), slots, limit, tuple(teams),
                  tuple(parse(p) for p in free_data.get('players', []) if p.get('status') == 'FREEAGENT'),
                  'ESPN read-only snapshot · weekly projections are full-week, game lock/bye status unavailable · '
                  'season is a full-season proxy · no verified ROS field; no ROS number produced',
                  datetime.now(timezone.utc).isoformat(), str(data['settings'].get('scoringSettings', {}).get('scoringType', 'League scoring')))


def load_espn():
    year, lid = os.getenv('ESPN_FANTASY_YEAR', '2026'), os.getenv('ESPN_LEAGUE_ID', '')
    if not lid.isdigit():
        raise ValueError('Set ESPN_LEAGUE_ID locally before selecting ESPN mode')
    s2, swid = os.getenv('ESPN_S2', ''), os.getenv('ESPN_SWID', '')
    cookie = f'espn_s2={s2}; SWID={swid}' if s2 and swid else ''
    data = espn_get(year, lid, ['mSettings', 'mRoster', 'mTeam'], cookie)
    free_data = espn_get(year, lid, ['mFreeAgents'], cookie, {'players': {'limit': 100, 'filterStatus': {'value': ['FREEAGENT']}}})
    return normalize_espn(data, free_data, year)
