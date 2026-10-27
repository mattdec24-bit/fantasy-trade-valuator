import json
import math
import random
import unittest
from dataclasses import replace
from evaluator.model import Engine, Player, Team, from_dict
from evaluator.sources import demo


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.league = demo()
        cls.engine = Engine(cls.league)

    def test_exact_optimizer_handles_flex_and_duplicate_slots(self):
        # A dual-eligible QB must be reserved for flex so the RB-only player can start.
        a = Player('a', 'Dual Player', 'QB', 'SYN', 20, 340, eligible=('RB',))
        b = Player('b', 'Runner Player', 'RB', 'SYN', 19, 323)
        league = replace(self.league, slots=('RB','OP'), teams=(Team('x','X',(a,b)),), free_agents=())
        lineup = Engine(league).lineup((a,b),'week')
        self.assertEqual(lineup['total'],39)
        self.assertEqual(lineup['coverage'],2)
        normal = self.engine.lineup(self.league.teams[0].players,'week')
        self.assertEqual(sum(p['slot']=='RB' for p in normal['lineup']),2)
        self.assertEqual(len({p['player_id'] for p in normal['lineup']}),9)

    def test_missing_zero_bye_started_and_injury_are_distinct(self):
        p = self.league.teams[0].players[0]
        for edited in [replace(p, weekly=None),replace(p,bye=True),replace(p,started=True),replace(p,status='OUT')]:
            e=Engine(replace(self.league,teams=(Team('x','X',(edited,)),)))
            self.assertEqual(e.lineup((edited,),'week')['coverage'],0)
        zero=replace(p,weekly=0)
        e=Engine(replace(self.league,teams=(Team('x','X',(zero,)),)))
        self.assertEqual(e.lineup((zero,),'week')['coverage'],1)
        for value in [float('nan'),float('inf'),'bad']:
            with self.assertRaises(ValueError): replace(p,weekly=value)

    def test_rejects_wrong_owner_duplicate_and_over_capacity(self):
        cases=[('harbor','orbit',['orbit-1'],['orbit-2']),('harbor','harbor',['harbor-1'],['harbor-2']),
               ('harbor','orbit',['harbor-1','harbor-1'],['orbit-1']),('harbor','orbit',[],['orbit-1']),
               ('harbor','orbit',['imaginary'],['orbit-1'])]
        for args in cases:
            with self.assertRaises(ValueError):self.engine.evaluate(*args)
        e=Engine(replace(self.league,roster_limit=12))
        with self.assertRaises(ValueError): e.evaluate('harbor','orbit',['harbor-2'],['orbit-5','orbit-6'])

    def test_deterministic_league_wide_and_validated(self):
        a=self.engine.candidates('harbor')
        b=Engine(from_dict(json.loads(json.dumps(self.league.public())))).candidates('harbor')
        self.assertEqual(a,b)
        self.assertEqual(a['opponents'],5)
        self.assertEqual(a['checked'],2205)
        self.assertGreater(a['qualified'],0)
        for c in a['candidates']:
            self.assertEqual(c,self.engine.evaluate(c['team_id'],c['other_id'],c['give'],c['receive']))
            self.assertGreater(min(c['yours']['season']['delta'],c['theirs']['season']['delta']),0)
            self.assertFalse(c['warnings'])

    def test_input_order_does_not_change_results(self):
        reversed_league=replace(self.league, teams=tuple(replace(t,players=tuple(reversed(t.players))) for t in reversed(self.league.teams)))
        e=Engine(reversed_league)
        self.assertEqual(self.engine.evaluate('harbor','orbit',['harbor-2','harbor-3'],['orbit-5','orbit-6']),e.evaluate('harbor','orbit',['harbor-3','harbor-2'],['orbit-6','orbit-5']))

    def test_incomplete_data_never_invented(self):
        t=self.league.teams[0]
        changed=replace(t, players=tuple(replace(p,season=None,weekly=None) for p in t.players))
        e=Engine(replace(self.league,teams=(changed,)+self.league.teams[1:]))
        result=e.evaluate('harbor','orbit',['harbor-2'],['orbit-5'])
        self.assertTrue(result['warnings'])
        self.assertEqual(e.candidates('harbor')['candidates'],[])

    def test_duplicate_ownership_and_unknown_slots_fail_closed(self):
        with self.assertRaises(ValueError):replace(self.league,teams=self.league.teams+(replace(self.league.teams[0],id='copy'),))
        with self.assertRaises(ValueError):replace(self.league,slots=('INVENTED',))

    def test_unsupported_lineup_horizons_fail_closed(self):
        for mode in ('ros', 'ROS', 'rest_of_season', '', None, 'season_active_only'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'Unsupported lineup horizon'):
                self.engine.lineup(self.league.teams[0].players, mode)

    def test_demo_primary_ranking_is_preserved(self):
        result = self.engine.candidates('harbor')
        self.assertEqual((result['checked'], result['qualified']), (2205, 38))
        self.assertEqual([c['id'] for c in result['candidates']], [
            '31767837ca139cb8', '823c8a3d240bd428', '85b06f4cfa6eb775',
            'a9fd4f8e2e0ee177', 'b78d4b3dfb02a4f8', 'e0d7eeddb6e5f0ae',
            '02722400f78e13fe', '18c89f50a30d5a7d', '5bf5436a8380e017',
            '678ea21ce22a2eda', '6812be8f180b5bad', '7fcf3633a52878d2'])
        self.assertEqual([c['score'] for c in result['candidates']], [8] * 6 + [6] * 6)
        self.assertTrue(all(c['verdict'] == 'Mutual upside' and not c['warnings']
                            for c in result['candidates']))

    def test_replacement_provenance_and_status_filtered_sensitivity(self):
        league = self.fit_league()
        # Primary deliberately includes all projected statuses; sensitivity only excludes known unavailable.
        free_agents = (
            Player('z-out', 'Synthetic OUT', 'RB', 'SYN', 0, 306, status='OUT'),
            Player('a-ir', 'Synthetic IR', 'RB', 'SYN', 0, 306, status='IR'),
            Player('doubtful', 'Synthetic Doubtful', 'RB', 'SYN', 0, 305, status='DOUBTFUL'),
            Player('ir-alias', 'Synthetic Injury Reserved', 'RB', 'SYN', 0, 304, status='INJURY RESERVED'),
            Player('suspended', 'Synthetic Suspended', 'RB', 'SYN', 0, 200, status='SUSPENDED'),
            Player('q', 'Synthetic Q', 'RB', 'SYN', 0, 289, status='QUESTIONABLE'),
            Player('active', 'Synthetic ACTIVE', 'RB', 'SYN', 0, 85, bye=True, started=True),
            Player('normal', 'Synthetic NORMAL', 'RB', 'SYN', 0, 84, status='NORMAL'),
            Player('healthy', 'Synthetic HEALTHY', 'RB', 'SYN', 0, 83, status='HEALTHY'),
            Player('unknown', 'Synthetic Unmapped Status', 'RB', 'SYN', 0, 82, status='UNMAPPED_STATUS'),
            Player('missing', 'Synthetic Missing', 'RB', 'SYN', 0, None),
            Player('negative', 'Synthetic Negative', 'TE', 'SYN', 0, -17),
            league.free_agents[1])
        # Current availability must not alter rostered full-season projections.
        teams = (replace(league.teams[0], players=(replace(league.teams[0].players[0], status='OUT'),)
                         + league.teams[0].players[1:]), league.teams[1])
        league = replace(league, teams=teams, free_agents=free_agents)
        engine = Engine(league)
        trade = engine.evaluate('a', 'b', ['a1'], ['b2'])
        model = trade['season_model']
        self.assertEqual((model['horizon'], model['divisor']), ('full_season', 17))
        self.assertEqual(model['primary_policy'], 'all_projected_free_agents')
        self.assertEqual(model['sensitivity_policy'], 'exclude_doubtful_out_ir_free_agents')
        rows = {r['position']: r for r in model['replacement']['primary']}
        self.assertEqual((rows['RB']['pool_count'], rows['RB']['projected_count'], rows['RB']['eligible_count']), (11, 10, 10))
        self.assertEqual(rows['RB']['selected']['id'], 'a-ir')  # Ties use ID, never source order.
        self.assertEqual(rows['RB']['selected']['status'], 'IR')
        self.assertEqual(rows['RB']['season_projection'], 306)
        self.assertEqual(rows['RB']['weekly_equivalent'], 18)
        self.assertTrue(rows['RB']['relevant'])
        self.assertFalse(rows['TE']['relevant'])
        self.assertEqual(rows['TE']['weekly_equivalent'], -1)  # No new baseline floor.
        filtered = {r['position']: r for r in model['replacement']['doubtful_out_ir_filtered']}
        self.assertEqual(filtered['RB']['selected']['id'], 'q')
        self.assertEqual(filtered['RB']['eligible_count'], 6)
        self.assertEqual(filtered['RB']['excluded_status_counts'], {
            'DOUBTFUL': 1, 'INJURY_RESERVED': 1, 'IR': 1, 'OUT': 1})
        self.assertNotIn('SUSPENDED', filtered['RB']['excluded_status_counts'])
        self.assertEqual(filtered['WR']['season_projection'], 0)  # Known zero, not missing.
        self.assertFalse(filtered['WR']['zero_fallback'])
        self.assertTrue(filtered['QB']['zero_fallback'])
        self.assertEqual(trade['yours']['season']['before']['total'], 3)
        self.assertEqual(trade['yours']['season']['delta'], 12)
        self.assertEqual(trade['sensitivity']['yours']['before']['total'], 4)
        self.assertEqual(trade['sensitivity']['yours']['delta'], 11)
        self.assertFalse(trade['sensitivity']['affects_ranking'])
        self.assertEqual(trade['score'], round(sum(trade[s]['season']['delta'] for s in ('yours', 'theirs'))
                                             + 2 * min(trade[s]['season']['delta'] for s in ('yours', 'theirs')), 2))
        other = Engine(replace(league, free_agents=tuple(reversed(free_agents))))
        self.assertEqual(trade, other.evaluate('a', 'b', ['a1'], ['b2']))
        self.assertEqual(model, engine.candidates('a')['season_model'])
        self.assertFalse(model['ros']['available'])
        self.assertIsNone(model['ros']['value'])
        self.assertIn('no verified ROS field', model['ros']['reason'])
        trade['season_model']['replacement']['primary'][0]['selected'] = {'id': 'invented'}
        trade['sensitivity']['yours']['before']['lineup'].clear()
        self.assertEqual(engine.evaluate('a', 'b', ['a1'], ['b2']), other.evaluate('a', 'b', ['a1'], ['b2']))

    def test_doubtful_out_ir_missing_baseline_is_separate_from_primary_warnings(self):
        league = self.fit_league()
        league = replace(league, free_agents=tuple(replace(p, status='OUT') for p in league.free_agents))
        engine = Engine(league)
        trade = engine.evaluate('a', 'b', ['a2'], ['b2'])
        self.assertEqual(trade['warnings'], [])
        self.assertEqual(trade['verdict'], 'Mutual upside')
        self.assertIn('RB, WR', trade['sensitivity']['warnings'][0])
        self.assertIn('zero baseline', trade['sensitivity']['warnings'][0])
        self.assertGreater(engine.candidates('a')['qualified'], 0)
        missing = Engine(replace(league, free_agents=()))
        self.assertEqual(missing.replacement['RB'], 0)
        self.assertTrue(any('zero baseline' in w for w in missing.evaluate('a', 'b', ['a2'], ['b2'])['warnings']))

    def fit_league(self):
        def p(pid, pos, points):
            return Player(pid, 'Synthetic ' + pid, pos, 'SYN', points, points * 17)
        return replace(self.league, slots=('RB', 'WR'), roster_limit=20, teams=(
            Team('a', 'A', (p('a1', 'RB', 20), p('a2', 'RB', 15), p('a3', 'WR', 1))),
            Team('b', 'B', (p('b1', 'WR', 20), p('b2', 'WR', 15), p('b3', 'RB', 1)))),
            free_agents=(p('fa-rb', 'RB', 0), p('fa-wr', 'WR', 0)))

    def test_replacement_warnings_only_for_startable_positions(self):
        league = self.fit_league()
        engine = Engine(league)
        self.assertEqual(engine.missing_replacement, [])
        trade = engine.evaluate('a', 'b', ['a2'], ['b2'])
        self.assertEqual(trade['warnings'], [])
        self.assertEqual(trade['verdict'], 'Mutual upside')
        self.assertGreater(engine.candidates('a')['qualified'], 0)
        self.assertEqual(Engine(replace(league, free_agents=())).missing_replacement, ['RB', 'WR'])
        self.assertEqual(Engine(replace(league, slots=('OP',))).missing_replacement, [])
        self.assertEqual(Engine(replace(league, slots=('RB/WR/TE',))).missing_replacement, [])
        # Explicit cross-position eligibility also makes its baseline relevant.
        dual = Player('dual', 'Synthetic Dual', 'QB', 'SYN', 10, 170, eligible=('WR',))
        teams = (replace(league.teams[0], players=league.teams[0].players + (dual,)), league.teams[1])
        self.assertEqual(Engine(replace(league, teams=teams)).missing_replacement, ['QB'])
        self.assertEqual(Engine(replace(league, free_agents=league.free_agents + (replace(dual, season=None),))).missing_replacement, [])

    def test_absent_rostered_positions_do_not_hide_relevant_data_gaps(self):
        league = self.fit_league()
        # Empty QB/TE slots are coverage gaps, not evidence for a rostered baseline.
        engine = Engine(replace(league, slots=('OP', 'TE'), free_agents=()))
        self.assertEqual(engine.missing_replacement, ['RB', 'WR'])
        warnings = engine.evaluate('a', 'b', ['a2'], ['b2'])['warnings']
        self.assertTrue(any('Incomplete projected lineup coverage' in w for w in warnings))
        self.assertTrue(any('No free-agent baseline for: RB, WR' in w for w in warnings))
        search = engine.candidates('a')
        self.assertEqual(search['candidates'], [])
        self.assertTrue(any('No free-agent baseline for: RB, WR' in w for w in search['warnings']))
        self.assertTrue(any('incomplete projected lineup coverage' in w for w in search['warnings']))
        # Free agents alone cannot make an otherwise absent position relevant.
        fa = Player('fa-qb', 'Synthetic FA', 'QB', 'SYN', 10, None, eligible=('WR',))
        self.assertEqual(Engine(replace(league, free_agents=league.free_agents + (fa,))).missing_replacement, [])
        # A rostered startable player still needs a baseline even with no projection.
        qb = replace(fa, id='a-qb')
        teams = (replace(league.teams[0], players=league.teams[0].players + (qb,)), league.teams[1])
        engine = Engine(replace(league, teams=teams))
        self.assertEqual(engine.missing_replacement, ['QB'])
        self.assertTrue(any('No free-agent baseline for: QB' in w for w in
                            engine.evaluate('a', 'b', ['a2'], ['b2'])['warnings']))

    def test_ineligible_players_filtered_before_shortlist_bound(self):
        league = self.fit_league()
        # Six high-projection bench-only QBs previously consumed the entire cap.
        teams = tuple(replace(t, players=t.players + tuple(
            Player(f'{t.id}-q{i}', 'Synthetic bench', 'QB', 'SYN', 100, 1700 + i)
            for i in range(6))) for t in league.teams)
        engine = Engine(replace(league, teams=teams))
        expected, actual = Engine(league).candidates('a'), engine.candidates('a')
        self.assertEqual(actual['checked'], expected['checked'])
        self.assertEqual(actual['qualified'], expected['qualified'])
        self.assertEqual([t['id'] for t in actual['candidates']], [t['id'] for t in expected['candidates']])
        self.assertTrue(all('-q' not in pid for t in actual['candidates'] for pid in t['give'] + t['receive']))
        # A QB with explicit starting-slot eligibility must survive the filter.
        dual = Player('a-dual', 'Synthetic Dual', 'QB', 'SYN', 11, 187, eligible=('WR',))
        changed = (replace(league.teams[0], players=(dual,)), league.teams[1])
        self.assertGreater(Engine(replace(league, teams=changed)).candidates('a', pool_size=1)['checked'], 0)

    def test_cached_lineups_and_evaluations_cannot_be_mutated(self):
        engine = Engine(self.fit_league())
        roster = engine.league.teams[0].players
        pristine = engine.lineup(roster, 'week')
        damaged = engine.lineup(roster, 'week')
        damaged['total'] = -999
        damaged['lineup'][0]['player_id'] = 'invented'
        damaged['lineup'].append({'slot': 'QB', 'player_id': 'invented'})
        self.assertEqual(engine.lineup(roster, 'week'), pristine)
        expected = engine.evaluate('a', 'b', ['a2'], ['b2'])
        damaged = engine.evaluate('a', 'b', ['a2'], ['b2'])
        damaged['yours']['week']['before']['lineup'].clear()
        damaged['theirs']['season']['after']['coverage'] = -1
        self.assertEqual(engine.evaluate('a', 'b', ['a2'], ['b2']), expected)

    def test_negative_projections_are_known_and_can_be_intentionally_benched(self):
        league = self.fit_league()
        teams = tuple(replace(t, players=tuple(replace(p, weekly=-i-1) for i, p in enumerate(t.players)))
                      for t in league.teams)
        engine = Engine(replace(league, teams=teams))
        lineup = engine.lineup(teams[0].players, 'week')
        self.assertEqual(lineup, {'total': 0, 'coverage': 2, 'filled': 0, 'benched_slots': 2,
                                  'slots': 2, 'lineup': []})
        trade = engine.evaluate('a', 'b', ['a2'], ['b2'])
        self.assertEqual(trade['warnings'], [])
        self.assertEqual(trade['verdict'], 'Mutual upside')
        self.assertGreater(engine.candidates('a')['qualified'], 0)
        # Missing projections still reduce coverage, and unavailable players do too.
        for changed in (replace(teams[0].players[-1], weekly=None), replace(teams[0].players[-1], bye=True)):
            changed_team = replace(teams[0], players=teams[0].players[:-1] + (changed,))
            e = Engine(replace(league, teams=(changed_team, teams[1])))
            self.assertEqual(e.lineup(changed_team.players, 'week')['coverage'], 1)
            self.assertTrue(any('Incomplete projected lineup coverage' in w for w in
                                e.evaluate('a', 'b', ['a2'], ['b2'])['warnings']))
        # Slot filling must not sacrifice points: assigning the dual player to RB
        # would cover both slots but lose to leaving the negative RB on the bench.
        dual = Player('dual', 'Synthetic Dual', 'WR', 'SYN', 20, 340, eligible=('RB',))
        negative = Player('negative', 'Synthetic Negative', 'RB', 'SYN', -5, -85)
        e = Engine(replace(league, teams=(Team('a', 'A', (dual, negative)),)))
        result = e.lineup((dual, negative), 'week')
        self.assertEqual((result['total'], result['coverage'], result['filled'], result['benched_slots']), (20, 2, 1, 1))
        self.assertEqual(e.lineup((negative,), 'season')['total'], 0)  # Existing season floor retained.

    def test_lineup_points_and_coverage_match_independent_exhaustive_oracle(self):
        # Slot-by-slot enumeration is independent of the production player/mask DP.
        # No search optimization is introduced; this checks the points objective
        # and known-data coverage independently on small synthetic lineups.
        rng = random.Random(17)
        allowed = {'RB': {'RB'}, 'WR': {'WR'}, 'RB/WR': {'RB', 'WR'}, 'OP': {'QB', 'RB', 'WR', 'TE'}}
        for case in range(60):
            slots = tuple(rng.choice(tuple(allowed)) for _ in range(rng.randint(1, 4)))
            roster = tuple(Player(str(i), 'Synthetic Oracle', rng.choice(('QB', 'RB', 'WR', 'TE')), 'SYN',
                                  rng.choice((None, -9, -1, 0, 4, 12)), rng.choice((None, -170, 0, 85, 340)),
                                  bye=rng.random() < .1, eligible=('RB',) if rng.random() < .2 else ())
                           for i in range(5))
            league = replace(self.league, slots=slots, teams=(Team('oracle', 'Oracle', roster),), free_agents=())
            engine = Engine(league)
            for mode in ('week', 'season'):
                outcomes = []
                def visit(index, used, total, filled):
                    if index == len(slots):
                        outcomes.append((total, filled))
                        return
                    visit(index + 1, used, total, filled)
                    for p in roster:
                        raw = p.weekly if mode == 'week' else p.season
                        if p.id in used or raw is None or (mode == 'week' and p.bye):
                            continue
                        if p.position in allowed[slots[index]] or slots[index] in p.eligible:
                            score = raw if mode == 'week' else max(raw / 17, 0)
                            visit(index + 1, used | {p.id}, total + score, filled + 1)
                visit(0, set(), 0, 0)
                result = engine.lineup(roster, mode)
                best = max(outcomes)
                with self.subTest(case=case, mode=mode):
                    self.assertEqual((result['total'], result['filled']), (round(best[0], 2), best[1]))
                    self.assertEqual(result['coverage'], max(n for _, n in outcomes))
