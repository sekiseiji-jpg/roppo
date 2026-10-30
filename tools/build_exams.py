#!/usr/bin/env python3
"""司法試験短答式試験の過去問を法務省サイトから取り、exams/*.js を作る。

    python3 tools/build_exams.py              # 未取得の年度だけ取る
    python3 tools/build_exams.py --force       # 全部取り直す
    python3 tools/build_exams.py --force r7 r6 # 指定した年度だけ
    python3 tools/build_exams.py --offline     # raw/exams/ から作り直すだけ

問題と正答は別のページに置かれているので、年度ごとに2つのURLを持つ。
PDFのID（/content/NNNNNNNNN.pdf）は法務省が差し替えることがあるため、
直書きせずに年度ページのHTMLから毎回拾う。
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'raw', 'exams')
OUT = os.path.join(ROOT, 'exams')
BASE = 'https://www.moj.go.jp'
# CloudFront が既定の User-Agent を 403 で弾くので、ブラウザのものを送る
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

# (年度キー, 表示名, 西暦, 問題ページ, 短答式試験結果ページ)
# 収録は民法債権法改正の施行（令和2年4月1日）以降に絞っている。
# それより前の年度は改正前の条文を前提にしており、アプリの条文と食い違う。
EXAMS = [
    ('r7', '令和7年', 2025, 'jinji08_00267', 'jinji08_00270'),
    ('r6', '令和6年', 2024, 'jinji08_00241', 'jinji08_00245'),
    ('r5', '令和5年', 2023, 'jinji08_00198', 'jinji08_00202'),
    ('r4', '令和4年', 2022, 'jinji08_00104', 'jinji08_00108'),
    ('r3', '令和3年', 2021, 'jinji08_00056', 'jinji08_00058'),
    ('r2', '令和2年', 2020, 'jinji08_00016', 'jinji08_00020'),
]

# 短答式は憲法・民法・刑法の3科目。法令キーはアプリの laws/*.js と揃える。
SUBJECTS = [('kenpo', '憲法'), ('minpo', '民法'), ('keiho', '刑法')]

# 合格に必要な成績の基準（各科目の40%点）。法務省の発表に基づく固定値。
MIN_RATE = 0.4

LAWNAMES = [
    ('憲法', 'kenpo'), ('民法', 'minpo'), ('刑法', 'keiho'),
    ('会社法', 'kaishaho'), ('商法', 'shoho'),
    ('民事訴訟法', 'minso'), ('刑事訴訟法', 'keiso'),
]


# ---------------------------------------------------------------- 取得

def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=120) as f:
        data = f.read()
    if binary:
        return data
    for enc in ('utf-8', 'cp932', 'euc_jp'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode('utf-8', 'replace')


def page_pdfs(page_id):
    """年度ページから（リンク文字列, PDFのURL）を並び順で返す。"""
    html = fetch('%s/jinji/shihoushiken/%s.html' % (BASE, page_id))
    out = []
    pat = re.compile(r'<a[^>]+href="([^"]*?/content/\d+\.pdf)"[^>]*>(.*?)</a>',
                     re.S | re.I)
    for m in pat.finditer(html):
        href = m.group(1)
        label = re.sub(r'<[^>]+>', '', m.group(2))
        label = re.sub(r'\s+', '', label).strip()
        out.append((label, href if href.startswith('http') else BASE + href))
    return out


def pick(links, subject):
    """リンク一覧から科目名に一致するものを選ぶ。

    問題ページには短答式（憲法・民法・刑法）と論文式（公法系など）が並ぶ。
    科目名の完全一致だけを拾えば短答式のものになる。
    """
    hits = [u for label, u in links if label == subject]
    if not hits:
        raise SystemExit('「%s」のPDFがページ内に見つからない' % subject)
    return hits[0]


def cached(name, url, force, offline):
    path = os.path.join(RAW, name)
    if os.path.exists(path) and not force:
        return path
    if offline:
        if os.path.exists(path):
            return path
        raise SystemExit('--offline だが %s が無い' % path)
    os.makedirs(RAW, exist_ok=True)
    sys.stderr.write('  取得 %s\n' % url)
    data = fetch(url, binary=True)
    if not data.startswith(b'%PDF'):
        raise SystemExit('PDFでないものが返った: %s' % url)
    with open(path, 'wb') as f:
        f.write(data)
    time.sleep(0.4)
    return path


# ---------------------------------------------------------------- 下ごしらえ

Z2H = {chr(0xFF10 + i): str(i) for i in range(10)}


def digits(s):
    """全角・半角混在の数字列を半角にする。"""
    return ''.join(Z2H.get(c, c) for c in s)


def num(s):
    return int(digits(s))


def intish(s):
    """数字だけのセルなら int、そうでなければ None。

    正答表には「※ 第6問の採点に当たっては、受験者全員を正答として…」のような
    注記が列の中に混ざることがあるので、数字かどうかを必ず確かめる。
    """
    s = digits((s or '').strip())
    return int(s) if re.fullmatch(r'\d{1,4}', s) else None


CIRCLED = {chr(0x2460 + i): str(i + 1) for i in range(20)}  # ①..⑳


def pdf_lines(path):
    """PDFのテキストを行の配列にする。ページ番号と表紙は落とす。"""
    import pymupdf
    doc = pymupdf.open(path)
    lines = []
    for page in doc:
        for raw in page.get_text().split('\n'):
            s = raw.rstrip()
            if not s.strip():
                continue
            if re.fullmatch(r'\s*-\s*\d+\s*-\s*', s):      # ページ番号
                continue
            if '短答式試験問題集' in s:                      # 表紙
                continue
            if re.fullmatch(r'\s*［[^］]{1,8}］\s*', s):     # ［憲法］の科目見出し
                continue
            lines.append(s.strip())
    doc.close()
    return lines


# 行頭にだけ現れる目印。PDFの折り返しは目印を持たないので、
# 目印のない行は直前の単位に continuation として足す。
RE_Q = re.compile(r'^〔第([０-９\d]+)問〕')
# ブロックの見出しは行全体が【…】のとき（または折り返しでその前半のとき）だけ。
# リード文の「【語句群】から適切なものを入れた場合、…」は見出しではなく本文。
RE_BLOCK_FULL = re.compile(r'^【[^【】]{1,10}】$')
RE_BLOCK_OPEN = re.compile(r'^【[^【】]{0,6}$')
# 区切りの「．」は全角のはずだが、半角の「.」＋空白で組まれている箇所がある
# （令和2年の刑法 第6問の選択肢３など）。どちらも受ける。
RE_STMT = re.compile(r'^([アイウエオカキクケコ])\s*[．.]\s*')
RE_OPT = re.compile(r'^([０-９\d]{1,2})\s*[．.]\s*')
RE_WORD = re.compile(r'^([ａ-ｚ])\s*[．.]\s*')
RE_KEEP = re.compile(r'^(?:学生[Ａ-Ｚａ-ｚ]|[ａ-ｚ]\s*[．.]|[アイウエオ]\s*[．.]|[①-⑳])')


def split_questions(lines):
    """行の配列を問ごとに切り分ける。各問は目印つきの単位の列になる。"""
    questions = []
    cur = None
    for line in lines:
        if RE_Q.match(line):
            cur = {'n': num(RE_Q.match(line).group(1)), 'units': []}
            questions.append(cur)
            cur['units'].append(['head', line])
            continue
        if cur is None:
            continue
        units = cur['units']
        kind = None
        if RE_BLOCK_FULL.match(line) or RE_BLOCK_OPEN.match(line):
            kind = 'block'
        elif RE_STMT.match(line):
            kind = 'stmt'
        elif RE_OPT.match(line):
            kind = 'opt'
        elif RE_WORD.match(line) and any(u[0] == 'block' for u in units):
            # 語句群の ａ． は、ブロックが始まっている問だけ目印として扱う。
            # 憲法の ａ説／ｂ説のように記述の中に出るものは continuation。
            kind = 'word'
        if kind:
            units.append([kind, line])
        else:
            # continuation。会話や語句の行は改行を保って読みやすくする。
            sep = '\n' if RE_KEEP.match(line) else ''
            units[-1][1] += sep + line
    return questions


# ---------------------------------------------------------------- 正答表

def answer_table(path):
    """正答PDFの表から {解答欄No: {ans, pt, note}} を作る。

    表は 問|No|解答|配点|備考 の5列が左右に2組（または3組）並ぶ。
    問・配点・備考は複数行にまたがる結合セルで、その文字が載る行は
    上下にずれる（第20問のラベルが3行目に出る、など）。だから
    「問ごと」には読まず、解答欄Noごとに、その行にある値を拾うだけにする。
    どの解答欄がどの問に属するかは問題文のリード文から決める。

    解答が空の解答欄もある（出題の不備で受験者全員を正答として扱った問）。
    その場合は ans を None のまま残し、注記を footnotes に集める。
    """
    import pymupdf
    doc = pymupdf.open(path)
    full = None
    by_no = {}
    footnotes = []
    for page in doc:
        text = page.get_text()
        m = re.search(r'満点\s*([０-９\d]+)', text)
        if m and full is None:
            full = num(m.group(1))
        for table in page.find_tables().tables:
            rows = table.extract()
            if not rows:
                continue
            head = [(c or '').strip() for c in rows[0]]
            if '解答' not in ''.join(head):
                continue
            for row in rows[1:]:
                for h in range(len(head) // 5):
                    cell = (list(row[h * 5:h * 5 + 5]) + [None] * 5)[:5]
                    qn, no, ans, pt, note = cell
                    for raw in cell:
                        s = re.sub(r'\s+', '', raw or '')
                        if s.startswith('※') and s not in footnotes:
                            footnotes.append(s)
                    ni = intish(no)
                    if ni is None:
                        continue
                    note = re.sub(r'\s+', '', note or '')
                    by_no[ni] = {
                        'ans': intish(ans),
                        'pt': intish(pt),
                        'note': '' if note.startswith('※') else note,
                    }
    doc.close()
    return full, by_no, footnotes


# ---------------------------------------------------------------- 問の組み立て

# 解答欄の書き方は年度でぶれる。令和2年は ［№１］（NUMERO SIGN）と
# [No.４]（半角角括弧）が同じ年のうちに混ざっている。
RE_NO = re.compile(r'[［\[]\s*(?:No\s*[.．]?|№)\s*([０-９\d]+)\s*[］\]]')
RE_PT = re.compile(r'（配点：([０-９\d]+)）')
RE_PARTIAL = re.compile(r'([０-９\d]+)問正解で部分点([０-９\d]+)点')


def law_refs(text, default_law):
    """本文から条番号を拾い、"法令キー:条番号" の列にする。"""
    out = []
    pat = re.compile(r'(憲法|民法|刑法|会社法|商法|民事訴訟法|刑事訴訟法)?'
                     r'第([０-９\d]+)条(?:の([０-９\d]+))?')
    for m in pat.finditer(text):
        name, art, branch = m.group(1), m.group(2), m.group(3)
        key = default_law
        if name:
            for label, k in LAWNAMES:
                if label == name:
                    key = k
                    break
        ref = '%s:%s' % (key, digits(art) + ('_' + digits(branch) if branch else ''))
        if ref not in out:
            out.append(ref)
    return out[:10]


def lead_slots(lead):
    """リード文の「（解答欄は、…）」から解答欄Noの列と問いの型を読む。

    正答表の「問」列は結合セルのラベル行がずれることがあり、
    区切りの根拠にできない。問題文は解答欄を明示しているので、そちらを使う。
    """
    nos = [num(x) for x in RE_NO.findall(lead)]
    if re.search(r'の順に', lead) and len(nos) >= 2:
        lo, hi = nos[0], nos[-1]
        if hi >= lo:
            return list(range(lo, hi + 1)), 'each'
        return nos, 'each'
    if '順不同' in lead:
        return nos, 'multi'
    return nos, None


def lead_topic(lead):
    """リード文の冒頭から論点の語を取る。条文検索の手がかりにする。

    民法・刑法の短答は条番号を書かないので、条文参照はほとんど取れない。
    「成年後見制度に関する次のアからオまでの…」の「成年後見制度」があれば、
    全文検索へ渡して条文を引ける。
    """
    head = re.split(r'に関する|について|に照らし|のうち|次の', lead, maxsplit=1)[0]
    head = re.sub(r'^(次の|後記|以下の)', '', head).strip()
    head = re.sub(r'（[^）]*）', '', head)
    if 2 <= len(head) <= 30 and not RE_NO.search(head):
        return head
    return None


def build_question(q, by_no, law):
    units = q['units']
    head = units[0][1]
    blocks, stmts, opts, words = [], [], [], []
    lead = RE_Q.sub('', head)
    lead = RE_PT.sub('', lead, count=1).strip()
    for kind, text in units[1:]:
        if kind == 'block':
            m = re.match(r'^【\s*([^】]*?)\s*】(.*)$', text, re.S)
            if m:
                blocks.append({'t': re.sub(r'\s+', '', m.group(1)),
                               's': m.group(2).strip('\n')})
            else:
                blocks.append({'t': '', 's': text})
        elif kind == 'stmt':
            m = RE_STMT.match(text)
            stmts.append({'m': m.group(1), 's': text[m.end():].strip()})
        elif kind == 'opt':
            m = RE_OPT.match(text)
            body = re.sub(r'\n+', '　', text[m.end():]).strip()
            opts.append({'n': num(m.group(1)), 's': body})
        elif kind == 'word':
            m = RE_WORD.match(text)
            words.append({'m': m.group(1), 's': text[m.end():].strip()})
        else:
            lead += text

    nos, kind = lead_slots(lead)
    if not nos:
        return None, '第%d問: 解答欄の番号が読めない' % q['n']
    if kind is None:
        kind = 'blank' if blocks else 'combo'

    problems = []
    slots = []
    for n in nos:
        if n not in by_no:
            problems.append('第%d問: 正答表に No.%d が無い' % (q['n'], n))
            continue
        slots.append({'no': n, 'ans': by_no[n]['ans']})
    if not slots:
        return None, '; '.join(problems)

    # 配点と備考は結合セルで行がずれるので、この問の解答欄の行から拾う
    rows = [by_no[s['no']] for s in slots]
    pts = [r['pt'] for r in rows if r['pt'] is not None]
    notes = [r['note'] for r in rows if r['note']]
    group = {'pt': pts[0] if pts else 0, 'note': notes[0] if notes else ''}
    if len(set(pts)) > 1:
        problems.append('第%d問: 配点が複数ある %s' % (q['n'], pts))
    # 解答が空の解答欄は、出題の不備で全員正答として扱われたもの
    blank = [s['no'] for s in slots if s['ans'] is None]

    # 最後の選択肢に（参照条文）がくっつくことがあるので切り離す
    refnote = None
    if opts:
        last = opts[-1]['s']
        m = re.search(r'（参照条文）', last)
        if m:
            opts[-1]['s'] = last[:m.start()].strip()
            refnote = last[m.end():].strip()
    for s in stmts:
        m = re.search(r'（参照条文）', s['s'])
        if m and refnote is None:
            refnote = s['s'][m.end():].strip()
            s['s'] = s['s'][:m.start()].strip()

    out = {
        'q': q['n'],
        'pt': group['pt'],
        'kind': kind,
        'lead': re.sub(r'\s+', '', lead),
        'slots': slots,
    }
    # 中身の無いブロックは落とす。【語句群】【記述】は見出しの次の行から
    # 語句や記述が別の単位として取れるので、見出しだけが残ると二重に出る。
    blocks = [b for b in blocks if b['s']]
    if blocks:
        out['blocks'] = blocks
    if stmts:
        out['stmts'] = stmts
    if opts:
        out['opts'] = opts
    if words:
        out['words'] = words
    if refnote:
        out['refText'] = refnote
    pm = RE_PARTIAL.search(group['note'] or '')
    if pm:
        out['partial'] = {'need': num(pm.group(1)), 'pt': num(pm.group(2))}
    if group['note']:
        out['note'] = group['note']
    if blank:
        out['anyOk'] = True

    refs = law_refs(out['lead'] + ''.join(s['s'] for s in stmts), law)
    if refs:
        out['refs'] = refs
    topic = lead_topic(out['lead'])
    if topic:
        out['topic'] = topic

    # かたちの整合を確かめる
    if kind == 'each' and len(stmts) != len(slots):
        problems.append('第%d問: 記述%d件に対し解答欄%d件'
                        % (q['n'], len(stmts), len(slots)))
    if kind in ('combo', 'blank', 'multi') and not opts:
        problems.append('第%d問: 選択肢が取れていない' % q['n'])
    if kind in ('combo', 'blank', 'multi') and opts:
        got = [o['n'] for o in opts]
        want_opts = list(range(1, len(got) + 1))
        if got != want_opts:
            # 番号が1から連続していないなら、取りこぼしか重複がある。
            # 選択肢の区切りが半角「.」で組まれていると起きる。
            problems.append('第%d問: 選択肢の番号が %s（1から連続していない）'
                            % (q['n'], got))
        hi = max(got)
        for s in slots:
            if s['ans'] is not None and s['ans'] > hi:
                problems.append('第%d問: 正解%d が選択肢数%d を超える'
                                % (q['n'], s['ans'], hi))
    MARKS = 'アイウエオカキクケコ'
    if stmts:
        got = ''.join(s['m'] for s in stmts)
        if got != MARKS[:len(stmts)]:
            problems.append('第%d問: 記述の記号が %s（アから連続していない）'
                            % (q['n'], got))
    if kind == 'each':
        for s in slots:
            if s['ans'] is not None and s['ans'] not in (1, 2):
                problems.append('第%d問: 個別正誤の正解が %d' % (q['n'], s['ans']))
    return out, ('; '.join(problems) if problems else None)


# ---------------------------------------------------------------- 出力

def build_subject(year, label, seiryaku, qpage, apage, law, subject, args):
    force = args.force
    offline = args.offline
    qname = '%s-%s.pdf' % (year, law)
    aname = '%s-%s-ans.pdf' % (year, law)
    if offline:
        qpath = cached(qname, '', False, True)
        apath = cached(aname, '', False, True)
    else:
        if not os.path.exists(os.path.join(RAW, qname)) or force:
            qurl = pick(page_pdfs(qpage), subject)
        else:
            qurl = ''
        qpath = cached(qname, qurl, force, offline)
        if not os.path.exists(os.path.join(RAW, aname)) or force:
            aurl = pick(page_pdfs(apage), subject)
        else:
            aurl = ''
        apath = cached(aname, aurl, force, offline)

    full, by_no, footnotes = answer_table(apath)
    questions = split_questions(pdf_lines(qpath))
    out, warns = [], []
    for q in questions:
        item, problem = build_question(q, by_no, law)
        if item is None:
            warns.append(problem)
            continue
        if problem:
            warns.append(problem)
        out.append(item)

    got_pt = sum(q['pt'] for q in out)
    if full and got_pt != full:
        warns.append('配点合計 %d が満点 %d と合わない' % (got_pt, full))
    slots = sum(len(q['slots']) for q in out)
    if slots != len(by_no):
        warns.append('解答欄 %d が正答表の %d と合わない' % (slots, len(by_no)))
    # 解答欄を一度ずつ使い切っているか。重複・取りこぼしをここで捕まえる
    used = {}
    for q in out:
        for s in q['slots']:
            used.setdefault(s['no'], []).append(q['q'])
    dup = sorted(n for n, qq in used.items() if len(qq) > 1)
    miss = sorted(set(by_no) - set(used))
    if dup:
        warns.append('解答欄の重複: %s' % ', '.join(
            'No.%d(第%s問)' % (n, '・'.join(map(str, used[n]))) for n in dup))
    if miss:
        warns.append('使われていない解答欄: %s'
                     % ', '.join('No.%d' % n for n in miss))

    data = {
        'key': '%s-%s' % (year, law),
        'year': year, 'yearLabel': label, 'seireki': seiryaku,
        'law': law, 'subject': subject,
        'full': full or got_pt,
        'pass': int(round((full or got_pt) * MIN_RATE)),
        'count': len(out),
        'slots': slots,
        'questions': out,
    }
    if footnotes:
        data['notes'] = footnotes
    return data, warns


def write_js(data):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, '%s.js' % data['key'])
    body = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('window.EXAMDATA=window.EXAMDATA||{};window.EXAMDATA[%s]=%s;\n'
                % (json.dumps(data['key']), body))
    return path, os.path.getsize(path)


def write_index(sets):
    path = os.path.join(OUT, 'index.js')
    idx = {
        'built': time.strftime('%Y-%m-%d'),
        'source': '法務省ウェブサイト（司法試験） https://www.moj.go.jp/jinji/shihoushiken/',
        'license': '公共データ利用規約（第1.0版）',
        'subjects': [{'law': k, 'name': n} for k, n in SUBJECTS],
        'sets': sets,
    }
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('window.EXAMS_INDEX=%s;\n'
                % json.dumps(idx, ensure_ascii=False, separators=(',', ':')))
    return path, os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('years', nargs='*', help='年度キー（r7 など）。省略で全部')
    ap.add_argument('--force', action='store_true', help='PDFを取り直す')
    ap.add_argument('--offline', action='store_true', help='raw/exams/ から作り直すだけ')
    args = ap.parse_args()

    targets = [e for e in EXAMS if not args.years or e[0] in args.years]
    if not targets:
        raise SystemExit('該当する年度が無い: %s' % ' '.join(args.years))

    sets, allwarn = [], []
    for year, label, seireki, qpage, apage in targets:
        for law, subject in SUBJECTS:
            sys.stderr.write('%s %s\n' % (label, subject))
            data, warns = build_subject(year, label, seireki, qpage, apage,
                                        law, subject, args)
            path, size = write_js(data)
            sys.stderr.write('  %d問 / 解答欄%d / 満点%d / %.0fKB\n'
                             % (data['count'], data['slots'], data['full'], size / 1024))
            for w in warns:
                sys.stderr.write('  ! %s\n' % w)
                allwarn.append('%s %s: %s' % (label, subject, w))
            sets.append({'key': data['key'], 'year': year, 'yearLabel': label,
                         'seireki': seireki, 'law': law, 'subject': subject,
                         'count': data['count'], 'slots': data['slots'],
                         'full': data['full'], 'pass': data['pass']})

    # index.js は既存のものと併せて書き直す（年度を指定して走らせた場合に消さない）
    if args.years:
        old = os.path.join(OUT, 'index.js')
        if os.path.exists(old):
            txt = open(old, encoding='utf-8').read()
            m = re.search(r'window\.EXAMS_INDEX=(.*);\s*$', txt, re.S)
            if m:
                prev = json.loads(m.group(1)).get('sets', [])
                keys = {s['key'] for s in sets}
                sets = sets + [s for s in prev if s['key'] not in keys]
    order = {e[0]: i for i, e in enumerate(EXAMS)}
    lawpos = {k: i for i, (k, _) in enumerate(SUBJECTS)}
    sets.sort(key=lambda s: (order.get(s['year'], 99), lawpos.get(s['law'], 99)))
    path, size = write_index(sets)
    sys.stderr.write('exams/index.js %d件 / %.1fKB\n' % (len(sets), size / 1024))

    if allwarn:
        sys.stderr.write('\n突き合わせで %d件の食い違い:\n' % len(allwarn))
        for w in allwarn:
            sys.stderr.write('  %s\n' % w)
        return 1
    sys.stderr.write('\n突き合わせの食い違いなし\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
