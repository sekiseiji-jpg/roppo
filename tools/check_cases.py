#!/usr/bin/env python3
"""判例データの見張り番。

    python3 tools/check_cases.py

次の3つを見る。
  1. 手書きの文（事件の通称・事案・ひとこと）に、日本語でない字が紛れていないか
     — 機械で書いた日本語には混入が起きる。構文エラーにならないので気づきにくい
  2. exam に書いた条文が、ほんとうに実在するか
  3. 司法試験で問われた条文のうち、まだ判例の付いていないものはどれか
"""

import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_js(path):
    """アプリの *.js データを読む。代入の形が2種類あるので、両方に対応する。

        window.CASES_INDEX={...}
        window.LAWDATA=window.LAWDATA||{};window.LAWDATA["minpo"]={...}

    「= のうしろがすぐ { か [ になっている最初の場所」が中身の始まり。
    = の個数で数えると、片方の形で必ず落ちる。
    """
    with open(path, encoding='utf-8') as f:
        src = f.read()
    m = re.search(r'=\s*(?=[\[{])', src)
    if not m:
        raise ValueError('データの始まりが見つかりません: %s' % path)
    return json.loads(src[m.end():].strip().rstrip(';'))


# 日本語の文に出てきてはいけない字。ラテン文字の語、ハングル、キリル文字。
STRAY = re.compile(r'[가-힯Ѐ-ӿ]|[A-Za-z]{2,}')
ALLOW = {'PDF', 'URL', 'WECPNL'}


def main():
    bad = 0

    print('=== 1. 手書きの文に紛れた日本語でない字 ===')
    from cases_seed import CASES, GROUPS
    for c in CASES:
        for field in ('name', 'facts', 'point'):
            for m in STRAY.finditer(c.get(field) or ''):
                if m.group() in ALLOW:
                    continue
                bad += 1
                print('  ✗ %-18s %s に「%s」' % (c['key'], field, m.group()))
    for g in GROUPS:
        for m in STRAY.finditer(g['name'] + g['desc']):
            if m.group() in ALLOW:
                continue
            bad += 1
            print('  ✗ 分野 %-14s に「%s」' % (g['id'], m.group()))
    print('  （問題なし）' if not bad else '  計 %d件' % bad)

    print('\n=== 2. exam に書いた条文が実在するか ===')
    nums, miss = {}, 0
    for c in CASES:
        for r in c.get('exam') or []:
            k, _, n = r.partition(':')
            if k not in nums:
                path = os.path.join(ROOT, 'laws', k + '.js')
                nums[k] = ({a['num'] for a in load_js(path)['articles']}
                           if os.path.exists(path) else None)
            if nums[k] is None or n not in nums[k]:
                miss += 1
                print('  ✗ %-18s %s' % (c['key'], r))
    print('  （問題なし）' if not miss else '  計 %d件' % miss)
    bad += miss

    print('\n=== 3. 出題された条文のうち、判例のないもの ===')
    exam_refs = collections.Counter()
    for g in sorted(glob.glob(os.path.join(ROOT, 'exams', '*.js'))):
        if g.endswith('index.js'):
            continue
        for q in load_js(g)['questions']:
            for r in q.get('refs') or []:
                exam_refs[r] += 1
    idx_path = os.path.join(ROOT, 'cases', 'index.js')
    have = set(load_js(idx_path)['byArticle']) if os.path.exists(idx_path) else set()
    gaps = [(c, r) for r, c in exam_refs.items() if r not in have]
    gaps.sort(reverse=True)
    for c, r in gaps[:20]:
        print('  %2d回  %s' % (c, r))
    covered = sum(c for r, c in exam_refs.items() if r in have)
    total = sum(exam_refs.values())
    print('  出題 %d件中 %d件（%d%%）は、判例の付いた条文' % (total, covered, round(covered * 100 / total)))
    print('  判例のない条文 %d / %d' % (len(gaps), len(exam_refs)))

    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
