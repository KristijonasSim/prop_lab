"""Hide total failures from the board: died at step 3 after repair, or under 1 trade/week.
Archives rows to backtests/factory/archive/<stamp>_pruned/ and keeps a carried stub
in tried.jsonl so nothing is re-tested. Kris, 2026-10-07. Dry run unless --apply."""
import json, ast, sys, collections
sys.path.insert(0, '.')
from factory import queue
from factory.dashboard import _fingerprint, script_of
D = queue.DIR
rows = lambda f: queue.rows(D / f)
tried = [r for r in rows('tried.jsonl') if not r.get('carried')]
surv = [r for r in rows('survivors.jsonl') if not r.get('carried')]
ideas = rows('ideas.jsonl')
# per-day of each idea's best cell, by name (latest record wins)
rate = {}
for x in ideas:
    s = x.get('score')
    try: s = ast.literal_eval(s) if isinstance(s, str) else s
    except Exception: s = None
    # Keyed by SCRIPT: a repaired variant is filed as "<name> [with trend]"
    # while its idea row keeps the bare name, and keying by full name missed
    # 105 of them on the first run. A script keeps its best variant's rate.
    if s and s.get('per_day') is not None:
        k = script_of(x['name']); rate[k] = max(rate.get(k, 0), s['per_day'])
st = {}
for r in surv + tried:
    fp = _fingerprint(r)
    e = st.setdefault(fp, {'reached': 0, 'died': 0, 'gate': '', 'name': r.get('name'), 'source': r.get('source')})
    if 'reached' in r: e['reached'] = max(e['reached'], int(r.get('reached') or 3))
    if r.get('died_at'): e['died'] = int(r['died_at']); e['gate'] = r.get('gate') or 'other'
why = {}
for fp, e in st.items():
    if e['died'] == 3: why[fp] = f"step3:{e['gate']}"
    elif e['died'] == 6 or e['reached'] >= 7:
        pd = rate.get(script_of(e['name']))
        if pd is not None and pd < 0.2: why[fp] = 'under 1 trade/week'
c = collections.Counter(why.values()); print('ideas', len(st), 'remove', len(why), dict(c))
print('by source', collections.Counter(st[f]['source'] for f in why))
kept = {f: e for f, e in st.items() if f not in why}
print('kept', len(kept), collections.Counter('scored' if e['reached']>=7 and not e['died'] else f"died{e['died']}" if e['died'] else 'alive' for e in kept.values()))
if '--apply' not in sys.argv: sys.exit()
from datetime import datetime, timezone
from factory.reset import _KEEP
dest = D / 'archive' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_pruned'); dest.mkdir(parents=True)
gone = set(why); gone_names = {script_of(st[f]['name']) for f in gone} - {script_of(e['name']) for e in kept.values()}
def split(f, test):
    allr = rows(f); out = [r for r in allr if test(r)]; keep = [r for r in allr if not test(r)]
    (dest / f).write_text(''.join(json.dumps(r) + '\n' for r in out))
    return keep, out
tk, tout = split('tried.jsonl', lambda r: not r.get('carried') and _fingerprint(r) in gone)
sk, sout = split('survivors.jsonl', lambda r: not r.get('carried') and _fingerprint(r) in gone)
ik, iout = split('ideas.jsonl', lambda r: script_of(r.get('name')) in gone_names)
stubs = {}
for r in tout + sout:
    stubs.setdefault(_fingerprint(r), {**{k: r[k] for k in _KEEP if k in r}, 'carried': 1})
w = lambda f, rs: (D / f).write_text(''.join(json.dumps(r, separators=(',', ':')) + '\n' for r in rs))
w('tried.jsonl', tk + list(stubs.values())); w('survivors.jsonl', sk); w('ideas.jsonl', ik)
(dest / 'WHY.json').write_text(json.dumps({st[f]['name']: why[f] for f in gone}, indent=1))
print('archived to', dest, 'tried', len(tout), 'surv', len(sout), 'ideas', len(iout), 'stubs', len(stubs))
