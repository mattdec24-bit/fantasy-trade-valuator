from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
from functools import lru_cache
from itertools import combinations
import hashlib
import math

POSITIONS = ('QB', 'RB', 'WR', 'TE', 'D/ST', 'K')
SLOT_POSITIONS = {p: {p} for p in POSITIONS} | {
    'RB/WR': {'RB', 'WR'}, 'WR/TE': {'WR', 'TE'},
    'RB/WR/TE': {'RB', 'WR', 'TE'}, 'OP': {'QB', 'RB', 'WR', 'TE'},
}
UNAVAILABLE = {'OUT', 'O', 'DOUBTFUL', 'IR', 'INJURY_RESERVE', 'INJURED_RESERVE',
               'INJURY_RESERVED', 'SUSPENDED'}
SEASON_BASELINE_EXCLUDED = {'OUT', 'O', 'DOUBTFUL', 'IR', 'INJURY_RESERVE',
                           'INJURED_RESERVE', 'INJURY_RESERVED'}


def status_code(status):
    return '_'.join(str(status or '').strip().upper().replace('-', ' ').split())


def is_unavailable(status):
    return status_code(status) in UNAVAILABLE


def finite(value):
    if value is None:
        return None
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ValueError('Projection must be a finite number or null') from None
    if not math.isfinite(n):
        raise ValueError('Projection must be finite')
    return round(n, 2)


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    position: str
    team: str
    weekly: float | None
    season: float | None
    status: str = 'ACTIVE'
    bye: bool = False
    started: bool = False
    eligible: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.id or not self.name or self.position not in POSITIONS:
            raise ValueError('Invalid player identity or unsupported position')
        object.__setattr__(self, 'weekly', finite(self.weekly))
        object.__setattr__(self, 'season', finite(self.season))


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    players: tuple[Player, ...]


@dataclass(frozen=True)
class League:
    name: str
    week: int
    season: int
    slots: tuple[str, ...]
    roster_limit: int
    teams: tuple[Team, ...]
    free_agents: tuple[Player, ...]
    source: str
    fetched_at: str
    scoring: str

    def __post_init__(self):
        all_players = [p for t in self.teams for p in t.players] + list(self.free_agents)
        if len({p.id for p in all_players}) != len(all_players):
            raise ValueError('Duplicate player ownership in source')
        if len({t.id for t in self.teams}) != len(self.teams):
            raise ValueError('Duplicate team identity')
        if not self.slots or len(self.slots) > 12 or any(s not in SLOT_POSITIONS for s in self.slots):
            raise ValueError('Unsupported starting lineup configuration')
        if any(len(t.players) > self.roster_limit for t in self.teams):
            raise ValueError('Roster exceeds configured capacity; resolve IR/roster slots first')

    def public(self):
        return asdict(self)


def from_dict(data):
    def player(p):
        return Player(**(p | {'eligible': tuple(p.get('eligible', []))}))
    return League(**(data | {
        'slots': tuple(data['slots']),
        'teams': tuple(Team(t['id'], t['name'], tuple(player(p) for p in t['players'])) for t in data['teams']),
        'free_agents': tuple(player(p) for p in data.get('free_agents', [])),
    }))


class Engine:
    def __init__(self, league):
        self.league = league
        self.teams = {t.id: t for t in league.teams}
        self.players = {p.id: p for t in league.teams for p in t.players}
        # A baseline matters only for positions that can enter this league's
        # starting lineup, including explicit cross-position eligibility.
        startable_positions = {p.position for p in self.players.values() if self._eligible_slots(p)}
        self._replacement = {}
        provenance = {}
        for policy in ('primary', 'doubtful_out_ir_filtered'):
            self._replacement[policy], provenance[policy] = {}, []
            for pos in POSITIONS:
                pool = [p for p in league.free_agents if p.position == pos]
                projected = [p for p in pool if p.season is not None]
                eligible = [p for p in projected if policy == 'primary' or status_code(p.status) not in SEASON_BASELINE_EXCLUDED]
                excluded_status_counts = {}
                if policy == 'doubtful_out_ir_filtered':
                    for player in projected:
                        status = status_code(player.status) or 'UNKNOWN'
                        if status in SEASON_BASELINE_EXCLUDED:
                            excluded_status_counts[status] = excluded_status_counts.get(status, 0) + 1
                selected = min(eligible, key=lambda p: (-p.season, p.id), default=None)
                baseline = selected.season / 17 if selected else 0
                self._replacement[policy][pos] = baseline
                provenance[policy].append({
                    'position': pos, 'relevant': pos in startable_positions,
                    'pool_count': len(pool), 'projected_count': len(projected), 'eligible_count': len(eligible),
                    'excluded_status_counts': dict(sorted(excluded_status_counts.items())),
                    'zero_fallback': selected is None,
                    'selected': ({'id': selected.id, 'name': selected.name, 'status': selected.status,
                                  'bye': selected.bye, 'started': selected.started} if selected else None),
                    'season_projection': selected.season if selected else None,
                    'weekly_equivalent': round(baseline, 2),
                })
        # Preserve the original all-projected baseline, including unavailable FAs.
        # Only serialized display values are rounded; DP uses the full quotient.
        self.replacement = self._replacement['primary']
        self.missing_replacement = [r['position'] for r in provenance['primary'] if r['relevant'] and r['zero_fallback']]
        self._sensitivity_warnings = []
        missing_filtered = [r['position'] for r in provenance['doubtful_out_ir_filtered'] if r['relevant'] and r['zero_fallback']]
        if missing_filtered:
            self._sensitivity_warnings.append('Doubtful/Out/IR-filtered sensitivity: no free-agent baseline for: '
                                              + ', '.join(missing_filtered) + '; zero baseline disclosed')
        self._season_model = {
            'horizon': 'full_season', 'divisor': 17,
            'primary_policy': 'all_projected_free_agents',
            'sensitivity_policy': 'exclude_doubtful_out_ir_free_agents',
            'replacement': provenance,
            'ros': {'available': False, 'value': None,
                    'reason': 'The current ESPN source has no verified ROS field; no ROS number is produced.'},
        }
        self._lineup = lru_cache(maxsize=12000)(self._compute_lineup)

    def _eligible_slots(self, player):
        return [i for i, slot in enumerate(self.league.slots)
                if player.position in SLOT_POSITIONS[slot] or slot in player.eligible]

    def _compute_lineup(self, ids, mode, policy='primary'):
        if mode not in ('week', 'season'):
            raise ValueError('Unsupported lineup horizon; choose week or season (full-season proxy)')
        # Exact assignment DP over slot masks: each player can be used only once.
        slots = self.league.slots
        dp = {0: (0.0, ())}
        for pid in ids:
            p = self.players[pid]
            raw = p.weekly if mode == 'week' else p.season
            if raw is None or (mode == 'week' and (p.bye or p.started or is_unavailable(p.status))):
                continue
            score = raw if mode == 'week' else max(0, raw / 17 - self._replacement[policy][p.position])
            options = self._eligible_slots(p)
            updates = dict(dp)
            for mask, (total, assignment) in dp.items():
                for i in options:
                    bit = 1 << i
                    if mask & bit:
                        continue
                    key = mask | bit
                    choice = (total + score, assignment + ((i, pid),))
                    old = updates.get(key)
                    if old is None or choice[0] > old[0] + 1e-9 or (abs(choice[0] - old[0]) < 1e-9 and choice[1] < old[1]):
                        updates[key] = choice
            dp = updates
        mask, (total, assigned) = max(dp.items(), key=lambda item: (item[1][0], item[0].bit_count(), -item[0]))
        # Every reachable mask remains in the DP, even if its best total is
        # negative. Coverage measures known, available slot assignments, while
        # the selected lineup still maximizes points and may bench negatives.
        coverage = max(m.bit_count() for m in dp)
        return {'total': round(total, 2), 'coverage': coverage, 'filled': mask.bit_count(),
                'benched_slots': coverage - mask.bit_count(), 'slots': len(slots),
                'lineup': [{'slot': slots[i], 'player_id': pid} for i, pid in sorted(assigned)]}

    def lineup(self, players, mode):
        if mode not in ('week', 'season'):
            raise ValueError('Unsupported lineup horizon; choose week or season (full-season proxy)')
        return deepcopy(self._lineup(tuple(sorted(p.id for p in players)), mode))

    def validate(self, team_id, other_id, give, receive):
        if team_id not in self.teams or other_id not in self.teams or team_id == other_id:
            raise ValueError('Choose two different rostered teams')
        if not isinstance(give, list) or not isinstance(receive, list) or not 1 <= len(give) <= 2 or not 1 <= len(receive) <= 2:
            raise ValueError('Select one or two players on each side')
        if any(not isinstance(p, str) for p in give + receive):
            raise ValueError('Player IDs must be strings')
        if len(set(give + receive)) != len(give + receive):
            raise ValueError('Players cannot appear twice')
        mine, other = self.teams[team_id], self.teams[other_id]
        if not set(give) <= {p.id for p in mine.players} or not set(receive) <= {p.id for p in other.players}:
            raise ValueError('Player ownership does not match the selected teams')
        if max(len(mine.players) - len(give) + len(receive), len(other.players) - len(receive) + len(give)) > self.league.roster_limit:
            raise ValueError('Trade exceeds roster capacity; no automatic drops are assumed')
        return mine, other

    def evaluate(self, team_id, other_id, give, receive):
        mine, other = self.validate(team_id, other_id, give, receive)
        sensitivity = {'policy': 'exclude_doubtful_out_ir_free_agents', 'affects_ranking': False,
                       'warnings': list(self._sensitivity_warnings)}
        def impact(team, outgoing, incoming):
            after = tuple(p for p in team.players if p.id not in outgoing) + tuple(self.players[i] for i in incoming)
            result = {}
            for mode in ('week', 'season'):
                before_lineup, after_lineup = self.lineup(team.players, mode), self.lineup(after, mode)
                result[mode] = {'before': before_lineup, 'after': after_lineup,
                                'delta': round(after_lineup['total'] - before_lineup['total'], 2)}
            result['depth'] = [{'position': pos, 'before': sum(p.position == pos for p in team.players),
                                'after': sum(p.position == pos for p in after)} for pos in POSITIONS]
            result['roster_before'], result['roster_after'] = len(team.players), len(after)
            return result
        yours = impact(mine, give, receive)
        theirs = impact(other, receive, give)
        for side, team, outgoing, incoming in (('yours', mine, give, receive), ('theirs', other, receive, give)):
            after_ids = tuple(sorted({p.id for p in team.players} - set(outgoing) | set(incoming)))
            before = deepcopy(self._lineup(tuple(sorted(p.id for p in team.players)), 'season', 'doubtful_out_ir_filtered'))
            after = deepcopy(self._lineup(after_ids, 'season', 'doubtful_out_ir_filtered'))
            sensitivity[side] = {'before': before, 'after': after, 'delta': round(after['total'] - before['total'], 2)}
        warnings = []
        for pid in give + receive:
            p = self.players[pid]
            if p.weekly is None or p.season is None:
                warnings.append(f'{p.name}: missing projection; no estimate invented')
            if p.status != 'ACTIVE' or p.bye or p.started:
                warnings.append(f'{p.name}: {p.status}' + (' · bye' if p.bye else '') + (' · game started' if p.started else ''))
        coverage = all(side[m][phase]['coverage'] == len(self.league.slots)
                       for side in (yours, theirs) for m in ('week', 'season') for phase in ('before', 'after'))
        if not coverage:
            warnings.append('Incomplete projected lineup coverage; treat deltas as partial totals')
        if self.missing_replacement:
            warnings.append('No free-agent baseline for: ' + ', '.join(self.missing_replacement) + '; zero baseline disclosed')
        mutual = yours['season']['delta'] > 0 and theirs['season']['delta'] > 0
        verdict = 'Mutual upside' if mutual else ('Your edge' if yours['season']['delta'] > 0 else 'Needs a closer look')
        if warnings:
            verdict = 'Review data / availability'
        identity = '|'.join([team_id, other_id, ','.join(sorted(give)), ','.join(sorted(receive))])
        score = round(min(yours['season']['delta'], theirs['season']['delta']) * 2 + yours['season']['delta'] + theirs['season']['delta'], 2)
        return {'id': hashlib.sha256(identity.encode()).hexdigest()[:16], 'team_id': team_id,
                'other_id': other_id, 'give': sorted(give), 'receive': sorted(receive), 'yours': yours,
                'theirs': theirs, 'score': score, 'verdict': verdict, 'warnings': warnings,
                'season_model': deepcopy(self._season_model), 'sensitivity': sensitivity,
                'explanation': f"Your projected starter value changes by {yours['season']['delta']:+.2f}; "
                               f"their value changes by {theirs['season']['delta']:+.2f} points per week above replacement. "
                               'This measures lineup fit, not market price or acceptance probability.'}

    def candidates(self, team_id, limit=12, pool_size=6):
        if team_id not in self.teams:
            raise ValueError('Unknown team')
        def packages(team):
            pool = sorted((p for p in team.players if self._eligible_slots(p)
                           and p.season is not None and p.weekly is not None
                           and not is_unavailable(p.status) and not p.bye and not p.started),
                          key=lambda p: (-p.season, p.id))[:pool_size]
            ids = sorted(p.id for p in pool)
            return [list(c) for n in (1, 2) for c in combinations(ids, n)]
        mine = packages(self.teams[team_id])
        results, checked = [], 0
        for other in sorted(self.teams.values(), key=lambda t: t.id):
            if other.id == team_id:
                continue
            for give in mine:
                for receive in packages(other):
                    try:
                        trade = self.evaluate(team_id, other.id, give, receive)
                    except ValueError:
                        continue
                    checked += 1
                    # Recommend only complete-data, strictly positive season fit for BOTH teams.
                    if not trade['warnings'] and min(trade['yours']['season']['delta'], trade['theirs']['season']['delta']) > 0:
                        results.append(trade)
        results.sort(key=lambda t: (-t['score'], t['id']))
        # Keep data gaps visible even when they disqualify every candidate.
        warnings = []
        if self.missing_replacement:
            warnings.append('No free-agent baseline for: ' + ', '.join(self.missing_replacement) + '; zero baseline disclosed')
        incomplete = sum(any(self.lineup(t.players, mode)['coverage'] < len(self.league.slots)
                             for mode in ('week', 'season')) for t in self.league.teams)
        if incomplete:
            warnings.append(f'{incomplete} team(s) have incomplete projected lineup coverage; search results may be limited')
        # Avoid filling the screen with near-identical packages; retain strongest per pair of packages.
        return {'candidates': results[:limit], 'checked': checked, 'qualified': len(results),
                'warnings': warnings,
                'season_model': deepcopy(self._season_model), 'sensitivity_warnings': list(self._sensitivity_warnings),
                'opponents': len(self.teams) - 1, 'pool_size': pool_size,
                'search': f'Top {pool_size} available starting-slot-eligible players by season projection per team; 1:1, 1:2, 2:1, 2:2. All opposing teams. No automatic drops.'}
