"""Regenerate the public synthetic fixture; no ESPN data is used."""
import json
from pathlib import Path

teams = []
profiles = [
    ('harbor', 'Harbor Hawks', [24, 25, 22, 20, 10, 9, 8, 7, 9, 7, 8, 6]),
    ('orbit', 'Orbit Owls', [22, 10, 9, 8, 25, 22, 20, 7, 10, 8, 8, 6]),
    ('canyon', 'Canyon Coyotes', [23, 14, 12, 11, 18, 17, 15, 13, 10, 8, 8, 6]),
    ('pine', 'Pine City Foxes', [24, 20, 18, 17, 12, 10, 9, 8, 11, 8, 8, 6]),
    ('metro', 'Metro Meteors', [21, 12, 10, 9, 22, 21, 18, 10, 11, 9, 8, 6]),
    ('coast', 'Coastal Comets', [25, 17, 14, 12, 16, 15, 14, 11, 12, 9, 8, 6]),
]
positions = ['QB', 'RB', 'RB', 'RB', 'WR', 'WR', 'WR', 'WR', 'TE', 'TE', 'D/ST', 'K']
first = ['Avery', 'Bennett', 'Cameron', 'Dorian', 'Ellis', 'Finley', 'Gray', 'Hayden', 'Indigo', 'Jules', 'Keegan', 'Lennox']
last = ['Vale', 'Ridge', 'North', 'Brook', 'Stone', 'Reed']
for ti, (tid, name, values) in enumerate(profiles):
    players = [dict(id=f'{tid}-{i+1}', name=f'{first[i]} {last[ti]}', position=pos,
                    team=f'SYN{ti+1}', weekly=v, season=v*17, status='ACTIVE', bye=False, started=False, eligible=[])
               for i, (pos, v) in enumerate(zip(positions, values))]
    teams.append(dict(id=tid, name=name, players=players))
fa = [dict(id=f'fa-{pos}', name=f'Reserve {pos}', position=pos, team='SYN', weekly=v,
           season=v*17, status='ACTIVE', bye=False, started=False, eligible=[])
      for pos, v in zip(['QB','RB','WR','TE','D/ST','K'], [15,6,6,5,4,4])]
league = dict(name='Founders League', week=7, season=2026, slots=['QB','RB','RB','WR','WR','TE','RB/WR/TE','D/ST','K'],
              roster_limit=15, teams=teams, free_agents=fa, source='Synthetic demo · no real players or private ESPN data',
              fetched_at='2026-10-20T00:00:00Z', scoring='Synthetic PPR projections')
Path('fixtures/demo.json').write_text(json.dumps(league, indent=2) + '\n')
