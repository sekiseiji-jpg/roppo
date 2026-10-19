#!/usr/bin/env python3
"""e-Gov 法令API から六法の条文を取得し、アプリ用の JSON に変換する。

    python3 tools/build_laws.py            # 全法令を取得して laws/ に書き出す
    python3 tools/build_laws.py 民法 刑法    # 指定した法令だけ更新する
    python3 tools/build_laws.py --offline   # 取得済みの raw/ から作り直すだけ

生成物
    laws/index.js     法令の一覧（アプリ起動時に読む軽いファイル）
    laws/<key>.js     法令ごとの条文（その法令を開いたときに読み込む）
    raw/<id>.json     APIの生データ（再変換用。アプリは読まない）

    fetch ではなく <script> で読み込む形にしてあるので、
    サーバーを立てずに index.html を直接開いても動く。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = 'https://laws.e-gov.go.jp/api/2/law_data/{id}?response_format=json'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, 'raw')
OUT_DIR = os.path.join(ROOT, 'laws')

# key, 法令ID, 表示名, 略称, 色, アイコン, ひとこと
LAWS = [
    ('kenpo',   '321CONSTITUTION',  '日本国憲法',  '憲法',  '#8b5e3c', '📜',
     '国のかたちと人権を定める最高法規。'),
    ('minpo',   '129AC0000000089',  '民法',        '民法',  '#2f6f4f', '🤝',
     '契約・家族・相続など、くらしの基本ルール。'),
    ('keiho',   '140AC0000000045',  '刑法',        '刑法',  '#9b3b3b', '⚖️',
     'どんな行為が犯罪で、どう罰せられるか。'),
    ('shoho',   '132AC0000000048',  '商法',        '商法',  '#2d5f8a', '🏪',
     '商人と商取引の特別ルール。'),
    ('kaishaho', '417AC0000000086', '会社法',      '会社',  '#1f6f78', '🏢',
     '会社のつくり方と動かし方。'),
    ('minso',   '408AC0000000109',  '民事訴訟法',  '民訴',  '#5b4b8a', '📑',
     '私人どうしの争いを裁判で解く手続。'),
    ('keiso',   '323AC0000000131',  '刑事訴訟法',  '刑訴',  '#7a4b2a', '🔍',
     '捜査から判決までの刑事手続。'),
]

# ---------- 取得 ----------

def fetch(law_id, force=False):
    """APIから生JSONを取ってきて raw/ に置く。すでにあれば使い回す。"""
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, law_id + '.json')
    if os.path.exists(path) and not force:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    url = API.format(id=law_id)
    req = urllib.request.Request(url, headers={'User-Agent': 'roppo-app/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                body = res.read().decode('utf-8')
            break
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                raise SystemExit('取得できませんでした: %s (%s)' % (law_id, e))
            time.sleep(2 * (attempt + 1))
    with open(path, 'w', encoding='utf-8') as f:
        f.write(body)
    return json.loads(body)


# ---------- XML(JSON化されたもの)を読む ----------

def kids(node, tag=None):
    out = []
    for c in node.get('children') or []:
        if isinstance(c, dict) and (tag is None or c.get('tag') == tag):
            out.append(c)
    return out


def kid(node, tag):
    for c in kids(node, tag):
        return c
    return None


def text_of(node):
    """ノード配下の文字をつなげる。ルビは親字だけ残す。"""
    if node is None:
        return ''
    buf = []
    for c in node.get('children') or []:
        if isinstance(c, str):
            buf.append(c)
        elif isinstance(c, dict):
            if c.get('tag') == 'Rt':
                continue          # よみがなは落とす
            buf.append(text_of(c))
    return ''.join(buf)


def sentences(node):
    """Sentence と Column を、読める順につなげる。

    ひとつの項の中の文どうしは続けて書く（法令集と同じ見た目）。
    号が表のように段組みされている Column どうしは全角空きで区切る。
    """
    out = ''
    for c in kids(node):
        tag = c.get('tag')
        if tag == 'Sentence':
            out += text_of(c)
        elif tag == 'Column':
            out += ('　' if out else '') + text_of(c)
        else:
            sub = sentences(c)
            if sub:
                out += ('　' if out else '') + sub
    return out


def read_items(node, tag, title_tag, sentence_tag, child_tag=None):
    out = []
    for it in kids(node, tag):
        entry = {
            't': text_of(kid(it, title_tag)).strip(),
            's': sentences(kid(it, sentence_tag) or {}),
        }
        if child_tag:
            sub = read_items(it, child_tag, child_tag + 'Title', child_tag + 'Sentence',
                             'Subitem2' if child_tag == 'Subitem1' else None)
            if sub:
                entry['sub'] = sub
        out.append(entry)
    return out


def read_table(struct):
    table = kid(struct, 'Table')
    if table is None:
        return None
    rows = []
    for tr in kids(table, 'TableRow'):
        rows.append([sentences(td) for td in kids(tr, 'TableColumn')])
    return rows or None


def read_paragraph(p):
    out = {'n': (p.get('attr') or {}).get('Num', '1'),
           's': sentences(kid(p, 'ParagraphSentence') or {})}
    cap = kid(p, 'ParagraphCaption')
    if cap is not None:
        out['cap'] = text_of(cap).strip()
    items = read_items(p, 'Item', 'ItemTitle', 'ItemSentence', 'Subitem1')
    if items:
        out['items'] = items
    tables = [t for t in (read_table(ts) for ts in kids(p, 'TableStruct')) if t]
    if tables:
        out['tables'] = tables
    return out


def read_article(a, path):
    num = (a.get('attr') or {}).get('Num', '')
    out = {
        'num': num,
        'k': text_of(kid(a, 'ArticleTitle')).strip(),   # 「第九条の二」など見出しそのもの
        'paras': [read_paragraph(p) for p in kids(a, 'Paragraph')],
    }
    cap = kid(a, 'ArticleCaption')
    if cap is not None:
        out['cap'] = text_of(cap).strip()
    if path:
        out['path'] = list(path)
    return out


LEVELS = [('Part', 'PartTitle', 1), ('Chapter', 'ChapterTitle', 2),
          ('Section', 'SectionTitle', 3), ('Subsection', 'SubsectionTitle', 4),
          ('Division', 'DivisionTitle', 5)]
LEVEL_BY_TAG = {tag: (title_tag, depth) for tag, title_tag, depth in LEVELS}


def walk_body(node, articles, toc, path):
    """本文を上から順にたどって、見出しと条文を平らに並べる。"""
    for c in kids(node):
        tag = c.get('tag')
        if tag == 'Article':
            art = read_article(c, path)
            art['i'] = len(articles)
            articles.append(art)
        elif tag in LEVEL_BY_TAG:
            title_tag, depth = LEVEL_BY_TAG[tag]
            title = text_of(kid(c, title_tag)).strip()
            toc.append({'d': depth, 't': title, 'a': len(articles)})
            walk_body(c, articles, toc, path + [title])


# ---------- 条番号 ----------

def num_sort_key(num):
    """"32_3_2" → (32, 3, 2)。並べ替えと条番号ジャンプに使う。

    削除された条がまとめられた "38:84"（第三十八条から第八十四条まで）は
    先頭の番号で並べる。
    """
    head = str(num).split(':')[0]
    return tuple(int(x) if x.isdigit() else 0 for x in head.split('_'))


def num_range(num):
    """"38:84" → [38, 84]。ふつうの条番号なら None。"""
    if ':' not in str(num):
        return None
    lo, _, hi = str(num).partition(':')
    try:
        return [int(lo.split('_')[0]), int(hi.split('_')[0])]
    except ValueError:
        return None


# ---------- 附則 ----------

def read_suppl(body):
    """附則を、改正法ごとのかたまりで読む。

    ひとかたまりは「附 則」という見出しと、条を並べたものか項を並べたものか
    のどちらか。制定時の附則が先で、あとは改正法の附則が続く。
    """
    out = []
    for sp in kids(body, 'SupplProvision'):
        attr = sp.get('attr') or {}
        block = {
            'label': text_of(kid(sp, 'SupplProvisionLabel')).strip() or '附則',
            'num': attr.get('AmendLawNum', ''),
        }
        if attr.get('Extract') == 'true':
            block['extract'] = True          # 抄録（必要な条だけ載せたもの）
        arts = [read_article(a, []) for a in kids(sp, 'Article')]
        for a in arts:
            a['sk'] = list(num_sort_key(a['num']))
        if arts:
            block['articles'] = arts
        paras = [read_paragraph(p) for p in kids(sp, 'Paragraph')]
        if paras:
            block['paras'] = paras
        if arts or paras:
            out.append(block)
    return out


# ---------- 変換 ----------

def convert(meta, data):
    key, law_id, title, short, color, icon, blurb = meta
    body = kid(data['law_full_text'], 'LawBody')
    info = data['law_info']
    rev = data['revision_info']

    preamble = []
    pre = kid(body, 'Preamble')
    if pre is not None:
        preamble = [sentences(kid(p, 'ParagraphSentence') or {}) for p in kids(pre, 'Paragraph')]

    articles, toc = [], []
    main = kid(body, 'MainProvision')
    if main is not None:
        walk_body(main, articles, toc, [])

    for a in articles:
        a['sk'] = list(num_sort_key(a['num']))   # 並べ替え・条番号ジャンプ用
        rng = num_range(a['num'])
        if rng:
            a['r'] = rng                          # 「第〇条から第〇条まで 削除」の範囲

    return {
        'key': key,
        'id': law_id,
        'title': title,
        'short': short,
        'color': color,
        'icon': icon,
        'blurb': blurb,
        'kana': (kid(body, 'LawTitle').get('attr') or {}).get('Kana', ''),
        'lawNum': text_of(kid(data['law_full_text'], 'LawNum')).strip(),
        'category': rev.get('category', ''),
        'promulgated': info.get('promulgation_date', ''),
        'enforced': rev.get('amendment_enforcement_date', ''),
        'revision': rev.get('law_revision_id', ''),
        'updated': rev.get('updated', ''),
        'preamble': preamble,
        'toc': toc,
        'articles': articles,
        'suppl': read_suppl(body),
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    offline = '--offline' in sys.argv
    force = '--force' in sys.argv
    targets = [m for m in LAWS if not args or m[2] in args or m[0] in args]
    if not targets:
        raise SystemExit('知らない法令です: %s' % ' '.join(args))

    os.makedirs(OUT_DIR, exist_ok=True)
    index = []
    for meta in LAWS:
        key, law_id, title = meta[0], meta[1], meta[2]
        out_path = os.path.join(OUT_DIR, key + '.js')
        if meta in targets:
            if offline and not os.path.exists(os.path.join(RAW_DIR, law_id + '.json')):
                print('  %s: raw がないので飛ばします' % title)
                continue
            print('  %s を変換中…' % title, end='', flush=True)
            law = convert(meta, fetch(law_id, force=force and not offline))
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('window.LAWDATA=window.LAWDATA||{};window.LAWDATA[%s]=' % json.dumps(key))
                json.dump(law, f, ensure_ascii=False, separators=(',', ':'))
                f.write(';\n')
            size = os.path.getsize(out_path)
            print(' 条文 %d / 附則 %d / %.1f KB'
                  % (len(law['articles']), len(law['suppl']), size / 1024))
        elif os.path.exists(out_path):
            with open(out_path, encoding='utf-8') as f:
                law = json.loads(f.read().split('=', 2)[2].rstrip().rstrip(';'))
        else:
            continue
        index.append({k: law[k] for k in ('key', 'title', 'short', 'color', 'icon', 'blurb',
                                          'kana', 'lawNum', 'category', 'promulgated',
                                          'enforced', 'updated')}
                     | {'count': len(law['articles']),
                        'suppl': len(law.get('suppl') or []),
                        'last': law['articles'][-1]['k'] if law['articles'] else ''})

    index.sort(key=lambda x: [m[0] for m in LAWS].index(x['key']))
    with open(os.path.join(OUT_DIR, 'index.js'), 'w', encoding='utf-8') as f:
        f.write('window.LAWS_INDEX=')
        json.dump({'built': time.strftime('%Y-%m-%d'),
                   'source': 'e-Gov 法令API（デジタル庁） https://laws.e-gov.go.jp/',
                   'laws': index}, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print('できました: %s' % OUT_DIR)


if __name__ == '__main__':
    main()
