#!/usr/bin/env python3
"""司法試験の過去問データから、出題された条文と論点を回数順に並べる。

    python3 tools/rank_exam_articles.py            # 条文を回数順に
    python3 tools/rank_exam_articles.py --topic    # 論点（topic）を回数順に
    python3 tools/rank_exam_articles.py --check    # 実在しない条文を指していないか
    python3 tools/rank_exam_articles.py --cases    # 判例がまだ無い条文を洗い出す

重要判例をどこから足すかを決めるのに使う。
出題回数の多い条文に判例が付いていなければ、そこが穴。
"""

import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_js(path):
    with open(path, encoding='utf-8') as f:
        return json.loads(f.read().split('=', 2)[2].strip().rstrip(';'))


def law_nums(key):
    path = os.path.join(ROOT, 'laws', key + '.js')
    if not os.path.exists(path):
        return None
    return {a['num']: a for a in load_js(path)['articles']}


def law_title(key):
    for m in load_js(os.path.join(ROOT, 'laws', 'index.js'))['laws']:
        if m['key'] == key:
            return m['short']
    return key


def collect():
    refs = collections.Counter()
    topics = collections.defaultdict(collections.Counter)
    where = collections.defaultdict(set)
    for g in sorted(glob.glob(os.path.join(ROOT, 'exams', '*.js'))):
        if g.endswith('index.js'):
            continue
        d = load_js(g)
        tag = os.path.basename(g).replace('.js', '')
        for q in d['questions']:
            for r in q.get('refs') or []:
                refs[r] += 1
                where[r].add('%s No.%s' % (tag, q['q']))
            if q.get('topic'):
                topics[d['law']][q['topic']] += 1
    return refs, topics, where


def case_refs():
    """すでに判例が付いている条文を集める。"""
    out = collections.Counter()
    idx = os.path.join(ROOT, 'cases', 'index.js')
    if not os.path.exists(idx):
        return out
    for g in load_js(idx)['groups']:
        path = os.path.join(ROOT, 'cases', g['id'] + '.js')
        if not os.path.exists(path):
            continue
        for c in load_js(path):
            for r in c.get('exam') or []:
                out[r] += 1
            for r in c.get('refs') or []:
                if 'law' in r:
                    out['%s:%s' % (r['law'], r['num'])] += 1
    return out


def main():
    refs, topics, where = collect()

    if '--check' in sys.argv:
        cache, bad = {}, 0
        for r, c in refs.items():
            k, _, n = r.partition(':')
            if k not in cache:
                cache[k] = law_nums(k)
            if cache[k] is None or n not in cache[k]:
                bad += 1
                print('✗ %-14s %s' % (r, '、'.join(sorted(where[r]))))
        print('参照 %d件中、実在しないもの %d件' % (sum(refs.values()), bad))
        return 1 if bad else 0

    if '--topic' in sys.argv:
        for law in ('kenpo', 'minpo', 'keiho'):
            print('=== %s ===' % law_title(law))
            for t, c in topics[law].most_common(40):
                print('  %3d  %s' % (c, t))
            print()
        return 0

    have = case_refs() if '--cases' in sys.argv else None
    cache = {}
    print('出題回数  条文                     判例  見出し')
    for r, c in refs.most_common():
        k, _, n = r.partition(':')
        if k not in cache:
            cache[k] = law_nums(k) or {}
        a = cache[k].get(n)
        cap = (a.get('cap') or a['k']) if a else '（実在しない）'
        if have is None:
            print('  %3d    %-22s      %s' % (c, '%s %s' % (law_title(k), a['k'] if a else n), cap))
        else:
            mark = '○' if have.get(r) else '—'
            if '--cases' in sys.argv and mark == '○':
                continue
            print('  %3d    %-22s  %s   %s' % (c, '%s %s' % (law_title(k), a['k'] if a else n), mark, cap))
    if have is not None:
        print('\n判例の付いていない条文を上に並べました（出題回数の多い順）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
