#!/usr/bin/env python3
"""data-study.js に書いた条番号が、laws/*.js の条文に実在するか確かめる。

    python3 tools/check_study.py          # 食い違いだけ出す
    python3 tools/check_study.py --all    # 全部の条文見出しを並べて出す
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_law(key):
    path = os.path.join(ROOT, 'laws', key + '.js')
    with open(path, encoding='utf-8') as f:
        return json.loads(f.read().split('=', 2)[2].strip().rstrip(';'))


def load_study():
    with open(os.path.join(ROOT, 'data-study.js'), encoding='utf-8') as f:
        src = f.read()
    body = src[src.index('{', src.index('window.STUDY')):src.rindex('};') + 1]
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    body = re.sub(r'^\s*//.*$', '', body, flags=re.M)
    body = re.sub(r',(\s*[}\]])', r'\1', body)              # 末尾コンマ
    body = re.sub(r'(^|[{,\s])([A-Za-z_]\w*)\s*:', r'\1"\2":', body)   # キーを引用符で
    body = body.replace("'", '"')
    return json.loads(body)


def main():
    show_all = '--all' in sys.argv
    study = load_study()
    cache, bad, total = {}, 0, 0
    for g in study['groups']:
        law = cache.setdefault(g['law'], load_law(g['law']))
        by_num = {a['num']: a for a in law['articles']}
        head = '\n[%s] %s（%s）' % (g['law'], g['name'], law['title'])
        printed = False
        for ref in g['arts']:
            total += 1
            a = by_num.get(ref['n'])
            if a is None or show_all:
                if not printed:
                    print(head)
                    printed = True
            if a is None:
                bad += 1
                near = [n for n in by_num if n.split('_')[0] == ref['n'].split('_')[0]]
                print('  ✗ %-8s 見つからない  (近い条: %s)' % (ref['n'], '、'.join(near[:5]) or 'なし'))
            elif show_all:
                print('  %-8s %-14s %s' % (ref['n'], a['k'], a.get('cap', '（見出しなし）')))
    print('\n条文 %d 件中、見つからないもの %d 件' % (total, bad))
    terms = study['terms']
    print('用語 %d 件 / 穴埋め語 %d 件 / 分野 %d 件'
          % (len(terms), len(study['blanks']), len(study['groups'])))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
