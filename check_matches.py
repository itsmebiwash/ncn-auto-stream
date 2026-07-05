import requests, json
HEADERS = {'X-Auth-Token': '3aa63d3143064fd2bbeb88f988c851d1'}
# Check next few days
r = requests.get('https://api.football-data.org/v4/matches?dateFrom=2026-07-04&dateTo=2026-07-08', headers=HEADERS, timeout=10)
data = r.json()
matches = data.get('matches', [])
print(f'Total matches: {len(matches)}')
for m in matches[:20]:
    sc = m['score']['fullTime']
    score = f"{sc['home']}-{sc['away']}" if sc['home'] is not None else "?"
    print(f"  {m['utcDate'][:10]} [{m['competition']['name']}] {m['homeTeam']['name']} {score} {m['awayTeam']['name']} | {m['status']}")
