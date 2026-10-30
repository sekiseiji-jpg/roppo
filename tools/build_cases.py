#!/usr/bin/env python3
"""裁判所ウェブサイトの裁判例検索から、重要判例を取ってきてアプリ用の JS にする。

    python3 tools/build_cases.py             # 未取得のものだけ取る
    python3 tools/build_cases.py --force     # 全部取り直す
    python3 tools/build_cases.py --offline   # raw_cases/ から作り直すだけ
    python3 tools/build_cases.py 尊属殺       # 名前で絞って取る

このスクリプトの肝は「記憶で書いた日付を、機械に確かめさせる」こと。
CASES には裁判年月日と、事件名に出てくるはずの語（expect）を書いておく。
日付で検索して expect に合う一件が見つからなければ、黙って進まずに失敗を報告する。
日付を覚え違えていたら、ここで必ず止まる。

生成物
    cases/index.js    判例の一覧と分野（起動時に読む）
    cases/<分野>.js    分野ごとの判例（その分野を開いたときに読む）
    raw_cases/<id>.html  取得した詳細ページ（再変換用。アプリは読まない）
"""

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, 'raw_cases')
OUT_DIR = os.path.join(ROOT, 'cases')
SEARCH = 'https://www.courts.go.jp/hanrei/search1/index.html'
DETAIL = 'https://www.courts.go.jp/hanrei/%s/detail%s/index.html'
UA = 'Mozilla/5.0 (Macintosh) roppo-app/1.0 (+https://sekiseiji-jpg.github.io/roppo/)'
WAIT = 1.5          # 裁判所のサーバーに負担をかけないよう、取得のあいだを空ける

# python3 -I で動かしてもスクリプトの隣を見つけられるようにする
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cases_seed import CASES, GROUPS          # noqa: E402  判例の種（手書き）


# ---------- 取得 ----------

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept-Language': 'ja',
        'Accept': 'text/html,application/xhtml+xml',
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.read().decode('utf-8', 'replace')
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                raise SystemExit('取得できませんでした: %s (%s)' % (url, e))
            time.sleep(3 * (attempt + 1))


def strip_tags(s):
    s = re.sub(r'<script.*?</script>|<style.*?</style>', '', s, flags=re.S)
    return html.unescape(re.sub(r'<[^>]+>', '\n', s))


def search_by_date(era, y, m, d, force=False):
    """裁判年月日で検索して、結果の行を構造化して返す。

    検索ページは1回あたり350KBほどあるので、日付ごとにキャッシュする。
    事件番号を足して絞り直すときに、同じ検索を何度も投げなくて済む。
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    cache = os.path.join(RAW_DIR, 'search-%s%d-%d-%d.html' % (era, y, m, d))
    if os.path.exists(cache) and not force:
        with open(cache, encoding='utf-8') as f:
            page = f.read()
    else:
        p = {
            'query1': '', 'query2': '',
            'filter[judgeDateMode]': '1',
            'filter[judgeGengoFrom]': era, 'filter[judgeYearFrom]': str(y),
            'filter[judgeMonthFrom]': str(m), 'filter[judgeDayFrom]': str(d),
        }
        page = get(SEARCH + '?' + urllib.parse.urlencode(p))
        with open(cache, 'w', encoding='utf-8') as f:
            f.write(page)
        time.sleep(WAIT)
    rows = []
    for mt in re.finditer(r'<tr[^>]*>(.*?)</tr>', page, re.S):
        row = mt.group(1)
        link = re.search(r'\.\./(\d+)/detail(\d)/', row)
        if not link:
            continue
        cells = [re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', c))).strip()
                 for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S)]
        rows.append({'id': link.group(1), 'kind': link.group(2),
                     'text': ' '.join(c for c in cells if c)})
    return rows


FIELDS = ['事件番号', '事件名', '裁判年月日', '法廷名', '裁判種別', '結果', '判例集等巻・号・頁',
          '原審裁判所名', '原審事件番号', '原審裁判年月日', '判示事項', '裁判要旨', '参照法条']


def fetch_detail(cid, kind, force=False):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, '%s.html' % cid)
    if os.path.exists(path) and not force:
        with open(path, encoding='utf-8') as f:
            page = f.read()
    else:
        page = get(DETAIL % (cid, kind))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)
        time.sleep(WAIT)
    lines = [l.strip() for l in strip_tags(page).split('\n') if l.strip()]
    out, i = {}, 0
    while i < len(lines):
        if lines[i] in FIELDS:
            key, vals, j = lines[i], [], i + 1
            while j < len(lines) and lines[j] not in FIELDS and lines[j] not in ('全文', 'ページ上部に戻る'):
                vals.append(lines[j])
                j += 1
            out[key] = '\n'.join(vals)
            i = j
        else:
            i += 1
    pdf = re.search(r'href="([^"]*hanrei-pdf-\d+\.pdf)"', page)
    out['pdf'] = 'https://www.courts.go.jp/assets/hanrei/%s' % os.path.basename(pdf.group(1)) if pdf else None
    return out


# ---------- 参照法条をアプリの条文参照に直す ----------

# アプリに入っている法令。ここにないものは、文字のまま出してリンクしない。
LAW_BY_NAME = {
    '憲法': 'kenpo', '日本国憲法': 'kenpo',
    '民法': 'minpo', '刑法': 'keiho', '商法': 'shoho', '会社法': 'kaishaho',
    '民事訴訟法': 'minso', '刑事訴訟法': 'keiso',
    '行政手続法': 'gyotetsu', '行政不服審査法': 'gyofufuku',
    '行政事件訴訟法': 'gyoso', '国家賠償法': 'kokubai', '行政代執行法': 'daishikko',
}
NAMES = sorted(LAW_BY_NAME, key=len, reverse=True)

KAN = {'〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
       '六': 6, '七': 7, '八': 8, '九': 9}


def kan2num(s):
    """「二〇〇」「百九十九」どちらの書き方も算用数字にする。"""
    if s.isdigit():
        return int(s)
    if all(c in KAN for c in s):                 # 二〇〇 のような位取りなしの書き方
        return int(''.join(str(KAN[c]) for c in s))
    total, cur = 0, 0
    for c in s:
        if c in KAN:
            cur = KAN[c]
        elif c == '十':
            total += (cur or 1) * 10
            cur = 0
        elif c == '百':
            total += (cur or 1) * 100
            cur = 0
        elif c == '千':
            total += (cur or 1) * 1000
            cur = 0
        else:
            return None
    return total + cur


ART_RE = re.compile(r'(?P<num>[0-9]+|[〇一二三四五六七八九十百千]+)条'
                    r'(?:の(?P<branch>[0-9]+|[〇一二三四五六七八九十百千]+))?')


JUNK_RE = re.compile(r'^[\s()（）0-9,，～〜・]*$')
PREFIX_RE = re.compile(r'^\([^)]*につき\)')


def parse_refs(text):
    """「憲法14条1項，刑法199条」→ [{'law':'kenpo','num':'14','t':'憲法14条1項'}, ...]

    法令名が出てきたら、次の法令名までは同じ法令の条として読む。

    参照法条は全角数字で書かれていることがあるので、先に NFKC で揃える。
    「(１～４につき)憲法１４条１項」のように裁判要旨の番号が頭に付くこともあるので、
    法令名は先頭だけでなく途中からでも拾う。
    """
    if not text:
        return []
    text = unicodedata.normalize('NFKC', text)
    out = []
    # 区切りは全角コンマ・読点・改行
    for part in re.split(r'[，,、\n]', text):
        part = PREFIX_RE.sub('', part.strip()).strip()
        if not part or JUNK_RE.match(part):
            continue
        law = None
        for nm in NAMES:
            if nm in part:
                law = LAW_BY_NAME[nm]
                break
        if law is None:
            # 前の項目と同じ法令が続いている場合（「憲法14条1項，1項」など）
            law = out[-1]['law'] if out and out[-1].get('law') else None
        m = ART_RE.search(part)
        if not m:
            out.append({'t': part})
            continue
        n = kan2num(m.group('num'))
        if n is None:
            out.append({'t': part})
            continue
        num = str(n)
        if m.group('branch'):
            b = kan2num(m.group('branch'))
            if b is not None:
                num += '_%d' % b
        out.append({'law': law, 'num': num, 't': part} if law else {'t': part})
    return out


def verify_refs(refs):
    """参照法条が、アプリに入っている条文として実在するか確かめる。

    刑法200条（尊属殺）のように削除された条は実在しない。リンクを外して文字だけ残す。
    """
    checked = []
    for r in refs:
        if 'law' not in r:
            checked.append(r)
            continue
        nums = law_nums(r['law'])
        if nums is None or r['num'] not in nums:
            checked.append({'t': r['t'], 'gone': True})
        else:
            checked.append(r)
    return checked


_nums_cache = {}


def law_nums(key):
    if key in _nums_cache:
        return _nums_cache[key]
    path = os.path.join(ROOT, 'laws', key + '.js')
    if not os.path.exists(path):
        _nums_cache[key] = None
        return None
    with open(path, encoding='utf-8') as f:
        law = json.loads(f.read().split('=', 2)[2].strip().rstrip(';'))
    _nums_cache[key] = {a['num'] for a in law['articles']}
    return _nums_cache[key]


# ---------- 照合 ----------

def resolve(case, force=False):
    """日付で検索し、expect に合う一件を選ぶ。選べなければ理由を返す。"""
    rows = search_by_date(case['era'], case['y'], case['m'], case['d'], force=force)
    if not rows:
        return None, 'その日付の裁判例が見つからない'
    hits = [r for r in rows if case['expect'] in r['text']]
    if case.get('court'):
        hits = [r for r in hits if case['court'] in r['text']]
    if not hits:
        sample = ' / '.join(r['text'][:48] for r in rows[:4])
        return None, 'expect「%s」に合う行がない（その日の裁判例: %s）' % (case['expect'], sample)
    if len(hits) > 1 and case.get('jiken'):
        hits = [r for r in hits if case['jiken'] in r['text']] or hits
    if len(hits) > 1:
        sample = ' / '.join(r['text'][:48] for r in hits)
        return None, '%d件に当たってしまう（jiken で事件番号を足して絞る: %s）' % (len(hits), sample)
    row = hits[0]
    d = fetch_detail(row['id'], row['kind'], force=force)
    # cite を書いておくと、判例集の巻号頁まで一致するか確かめる。
    # 同じ日に同じ事件名が並ぶときの取り違えは、これでないと気づけない。
    if case.get('cite') and case['cite'] not in (d.get('判例集等巻・号・頁') or ''):
        return None, 'cite「%s」と判例集が合わない（取れたのは「%s」／%s %s）' % (
            case['cite'], d.get('判例集等巻・号・頁') or '（登載なし）',
            d.get('事件番号', ''), d.get('事件名', ''))
    return (row, d), None


def build_case(case, row, d):
    refs = verify_refs(parse_refs(d.get('参照法条', '')))
    return {
        'key': case['key'],
        'name': case['name'],
        'group': case['group'],
        'id': row['id'],
        'kind': row['kind'],
        'court': d.get('法廷名', ''),
        'type': d.get('裁判種別', ''),
        'date': d.get('裁判年月日', ''),
        'jiken': d.get('事件番号', ''),
        'title': d.get('事件名', ''),
        'result': d.get('結果', ''),
        'source': d.get('判例集等巻・号・頁', ''),
        'issue': d.get('判示事項', ''),
        'held': d.get('裁判要旨', ''),
        'refsText': d.get('参照法条', ''),
        'refs': refs,
        'exam': case.get('exam', []),
        'facts': case.get('facts', ''),
        'point': case.get('point', ''),
        'url': 'https://www.courts.go.jp/hanrei/%s/detail%s/index.html' % (row['id'], row['kind']),
        'pdf': d.get('pdf'),
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    offline = '--offline' in sys.argv
    targets = [c for c in CASES
               if not args or any(a in c['name'] or a == c['key'] for a in args)]
    if not targets:
        raise SystemExit('その名前の判例は CASES にありません: %s' % ' '.join(args))

    os.makedirs(OUT_DIR, exist_ok=True)
    built, failed = [], []
    for case in targets:
        print('  %-28s ' % case['name'], end='', flush=True)
        if offline:
            print('（--offline では日付照合を飛ばせません）')
            continue
        got, why = resolve(case, force=force)
        if why:
            print('✗ %s' % why)
            failed.append((case['name'], why))
            continue
        row, d = got
        rec = build_case(case, row, d)
        built.append(rec)
        linked = sum(1 for r in rec['refs'] if 'law' in r)
        print('✓ %s %s（参照法条 %d件・うちリンク %d件）'
              % (rec['date'], rec['source'] or '（判例集未登載）', len(rec['refs']), linked))

    by_group = {}
    for rec in built:
        by_group.setdefault(rec['group'], []).append(rec)
    for gid, recs in by_group.items():
        path = os.path.join(OUT_DIR, gid + '.js')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('window.CASEDATA=window.CASEDATA||{};window.CASEDATA[%s]=' % json.dumps(gid))
            json.dump(recs, f, ensure_ascii=False, separators=(',', ':'))
            f.write(';\n')

    index = []
    for g in GROUPS:
        recs = by_group.get(g['id'], [])
        if not recs:
            continue
        index.append(dict(g, count=len(recs),
                          cases=[{'key': r['key'], 'name': r['name'], 'date': r['date'],
                                  'court': r['court'], 'source': r['source'],
                                  'exam': r['exam']} for r in recs]))

    # 条文 → 判例 の逆引き。条文を開いたときに「この条文の判例」を出すために使う。
    # 参照法条だけでなく、試験で問われた条文（exam）からも引けるようにする。
    by_article = {}
    for rec in built:
        refs = {'%s:%s' % (r['law'], r['num']) for r in rec['refs'] if 'law' in r}
        refs.update(rec['exam'])
        for ref in sorted(refs):
            by_article.setdefault(ref, []).append(
                {'g': rec['group'], 'k': rec['key'], 'n': rec['name']})

    with open(os.path.join(OUT_DIR, 'index.js'), 'w', encoding='utf-8') as f:
        f.write('window.CASES_INDEX=')
        json.dump({'built': time.strftime('%Y-%m-%d'),
                   'source': '裁判所ウェブサイト 裁判例検索 https://www.courts.go.jp/app/hanrei_jp/',
                   'groups': index, 'byArticle': by_article},
                  f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print('条文から引ける判例: %d条' % len(by_article))

    print('\n取れたもの %d件 / 取れなかったもの %d件' % (len(built), len(failed)))
    for name, why in failed:
        print('  ✗ %s — %s' % (name, why))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
