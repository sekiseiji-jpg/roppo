/* 六法全書 - アプリ本体
   条文は laws/*.js（e-Gov法令APIから生成）、重要条文と用語は data-study.js。
   学習記録はこの端末の localStorage にだけ保存する。 */
'use strict';

const KEY = 'roppo-v1';
const INDEX = window.LAWS_INDEX;
const METAS = INDEX.laws;
const META = {};
METAS.forEach((m) => { META[m.key] = m; });
window.LAWDATA = window.LAWDATA || {};

const defaults = {
  read: {},        // groupId -> true（重要条文の分野を開いた）
  qstat: {},       // qid -> {o: 出題数, x: 誤答数}
  lawstat: {},     // lawKey -> {o, c}
  groupstat: {},   // groupId -> {o, c}
  savedArts: [],   // "law:num"
  savedQuiz: [],   // qid
  memos: {},       // "law:num" -> メモ本文
  sessions: [],    // {d, n, c}
  days: {},        // 日付 -> その日に解いた問題数
  lastLaw: 'kenpo',
  set: { shuffle: true, cap: true, fontsize: 16, theme: 'auto' },
};
let S = load();

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '{}');
    return Object.assign({}, defaults, raw, { set: Object.assign({}, defaults.set, raw.set || {}) });
  } catch (e) { return JSON.parse(JSON.stringify(defaults)); }
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* 容量超過などは無視 */ }
}

/* ========== 小さな道具 ========== */
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩', '⑪', '⑫', '⑬', '⑭', '⑮', '⑯', '⑰', '⑱', '⑲', '⑳'];
const ref = (law, num) => law + ':' + num;

function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove('show'), 1800);
}
function shuffle(a) {
  const r = a.slice();
  for (let i = r.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [r[i], r[j]] = [r[j], r[i]]; }
  return r;
}
function sample(arr, n) { return shuffle(arr).slice(0, n); }
function pct(c, o) { return o ? Math.round((c / o) * 100) : 0; }
function today() { return new Date().toISOString().slice(0, 10); }
function norm(s) { return String(s).normalize('NFKC').toLowerCase(); }

/* 条文のテキストをひとつながりにする（検索とクイズ用） */
function artText(a) {
  const out = [];
  (a.paras || []).forEach((p) => {
    if (p.cap) out.push(p.cap);
    if (p.s) out.push(p.s);
    (p.items || []).forEach((it) => {
      out.push(it.t + '　' + it.s);
      (it.sub || []).forEach((s2) => out.push(s2.t + '　' + s2.s));
    });
    (p.tables || []).forEach((rows) => rows.forEach((r) => out.push(r.join('　'))));
  });
  return out.join('\n');
}

/* ========== 法令データの読み込み ========== */
const pending = {};
function loadLaw(key) {
  if (window.LAWDATA[key]) return Promise.resolve(window.LAWDATA[key]);
  if (pending[key]) return pending[key];
  pending[key] = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'laws/' + key + '.js?v=4';
    s.onload = () => (window.LAWDATA[key] ? resolve(window.LAWDATA[key]) : reject(new Error(key)));
    s.onerror = () => reject(new Error(key));
    document.head.appendChild(s);
  });
  pending[key].catch(() => { delete pending[key]; });
  return pending[key];
}
function loadLaws(keys, onProgress) {
  let done = 0;
  return Promise.all(keys.map((k) => loadLaw(k).then((law) => {
    done += 1;
    if (onProgress) onProgress(done, keys.length);
    return law;
  })));
}
function findArt(law, num) { return law.articles.find((a) => a.num === num); }

/* ========== タブ ========== */
$$('.tab').forEach((t) => t.addEventListener('click', () => {
  $$('.tab').forEach((x) => x.classList.toggle('active', x === t));
  const name = t.dataset.tab;
  $$('.panel').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + name));
  if (name === 'stats') renderStats();
  if (name === 'saved') renderSaved();
  if (name === 'quiz') updatePool();
  window.scrollTo({ top: 0 });
}));
function goTab(name) {
  const t = $('.tab[data-tab="' + name + '"]');
  if (t) t.click();
}

/* ========================================================
   法令一覧
   ======================================================== */
function renderLawGrid() {
  $('#law-grid').innerHTML = METAS.map((m) => `
    <button class="law-card" style="--ec:${m.color}" data-law="${m.key}">
      <div class="lc-top"><span class="lc-icon">${m.icon}</span>
        <div><div class="lc-name">${esc(m.title)}</div>
        <div class="lc-kana">${esc(m.kana)}</div></div></div>
      <div class="lc-blurb">${esc(m.blurb)}</div>
      <div class="lc-meta"><span>${esc(m.lawNum)}</span><span>全${m.count}条</span>${
        m.suppl ? `<span>附則${m.suppl}件</span>` : ''}<span>施行 ${esc(m.enforced)}</span></div>
    </button>`).join('');
  $$('#law-grid .law-card').forEach((b) => b.addEventListener('click', () => openLaw(b.dataset.law)));
  $('#law-source').textContent =
    '出典: ' + INDEX.source + '（' + INDEX.built + ' 時点の条文）。'
    + '官報と異なる場合は官報が優先します。⚙ 設定に詳しい断り書きがあります。';
}

/* ========================================================
   法令の中身（目次と条文）
   ======================================================== */
let curLaw = null;        // 表示中の法令データ
let sections = [];        // {d, t, kind, from, to, path}  kind: main / pre / suppl
let curSec = -1;
let shown = 0;            // 今どこまで描いたか（本則は条数、附則はかたまりの数）
const PAGE = 60;          // 本則をいちどに描く条数
const PAGE_SUPPL = 10;    // 附則をいちどに描くかたまりの数

function buildSections(law) {
  const toc = law.toc || [];
  const list = [];
  if (law.preamble && law.preamble.length) {
    list.push({ d: 1, t: '前文', kind: 'pre', from: -1, to: -1, path: [] });
  }
  if (!toc.length) {
    if (law.articles.length) {
      list.push({ d: 1, t: '本則', kind: 'main', from: 0, to: law.articles.length, path: [] });
    }
  } else {
    if (toc[0].a > 0) list.push({ d: 1, t: '冒頭', kind: 'main', from: 0, to: toc[0].a, path: [] });
    const path = [];
    toc.forEach((e, i) => {
      // 同じ深さ以下の見出しが次に来るところまでが、この見出しの守備範囲
      let to = law.articles.length;
      for (let j = i + 1; j < toc.length; j++) {
        if (toc[j].d <= e.d) { to = toc[j].a; break; }
      }
      path.length = Math.max(0, e.d - 1);
      while (path.length < e.d - 1) path.push('');
      list.push({ d: e.d, t: e.t, kind: 'main', from: e.a, to, path: path.slice() });
      path[e.d - 1] = e.t;
    });
  }
  // 附則は改正法ごとに分かれているが、目次ではひとつにまとめる
  if ((law.suppl || []).length) {
    list.push({ d: 1, t: '附則', kind: 'suppl', from: -1, to: -1, path: [] });
  }
  return list;
}

function openLaw(key, opts) {
  const o = opts || {};
  $('#law-grid').innerHTML = '<div class="loading">条文を読み込んでいます…</div>';
  loadLaw(key).then((law) => {
    curLaw = law;
    S.lastLaw = key;
    save();
    sections = buildSections(law);
    const m = META[key];
    $('#law-list-view').classList.add('hidden');
    $('#law-detail-view').classList.remove('hidden');
    $('#law-hero').style.setProperty('--ec', m.color);
    $('#law-hero').innerHTML = `
      <div class="lc-top"><span class="lh-icon">${m.icon}</span>
        <div><h2>${esc(law.title)}</h2><div class="lh-kana">${esc(law.kana)}</div></div></div>
      <div class="lh-blurb">${esc(m.blurb)}</div>
      <div class="lh-meta"><span>${esc(law.lawNum)}</span><span>全${law.articles.length}条</span>${
        (law.suppl || []).length ? `<span>附則${law.suppl.length}件</span>` : ''}
        <span>公布 ${esc(law.promulgated)}</span><span>最終改正の施行 ${esc(law.enforced)}</span></div>`;
    if (o.suppl != null) {
      const si = sections.findIndex((x) => x.kind === 'suppl');
      if (si >= 0) { openSection(si, o.num || null, o.suppl); return; }
    }
    if (o.num != null) {
      const idx = law.articles.findIndex((a) => a.num === o.num);
      if (idx >= 0) { openSection(sectionOf(idx), o.num); return; }
    }
    showToc();
  }).catch(() => {
    renderLawGrid();
    toast('条文ファイルを読み込めませんでした');
  });
}

function sectionOf(artIndex) {
  // その条文を含む、いちばん細かい章立てを選ぶ
  let best = -1;
  sections.forEach((s, i) => {
    if (s.from <= artIndex && artIndex < s.to) {
      if (best < 0 || s.d >= sections[best].d) best = i;
    }
  });
  return best < 0 ? 0 : best;
}

function showToc() {
  $('#law-toc-view').classList.remove('hidden');
  $('#law-arts-view').classList.add('hidden');
  renderToc();
  window.scrollTo({ top: 0 });
}

function renderToc() {
  const q = norm($('#toc-filter').value.trim());
  const rows = sections
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => !q || norm(s.t).includes(q));
  $('#law-toc').innerHTML = rows.length ? rows.map(({ s, i }) => {
    const n = s.kind === 'suppl' ? curLaw.suppl.length + '件'
      : s.kind === 'pre' ? ''
        : (s.to - s.from) + '条';
    return `<button class="toc-row d${Math.min(s.d, 5)}" data-sec="${i}">
      <span>${esc(s.t)}</span><span class="tc-n">${n}</span></button>`;
  }).join('') : '<div class="empty">見つかりませんでした</div>';
  $$('#law-toc .toc-row').forEach((b) => b.addEventListener('click', () => openSection(+b.dataset.sec)));
}
$('#toc-filter').addEventListener('input', renderToc);

function openSection(i, highlightNum, supplIdx) {
  curSec = i;
  const s = sections[i];
  $('#law-toc-view').classList.add('hidden');
  $('#law-arts-view').classList.remove('hidden');
  const crumbs = s.path.filter(Boolean);
  $('#sec-title').innerHTML =
    (crumbs.length ? `<span class="sh-path">${esc(crumbs.join(' › '))}</span>` : '')
    + esc(s.t)
    + (s.kind === 'suppl' ? '<span class="sh-path">改正法ごとに新しいものが下に並びます</span>' : '');
  $('#btn-sec-prev').disabled = i <= 0;
  $('#btn-sec-next').disabled = i >= sections.length - 1;
  shown = 0;
  $('#art-list').innerHTML = '';
  $('#btn-art-more').classList.add('hidden');
  if (s.kind === 'pre') $('#art-list').innerHTML = renderPreamble();
  else if (s.kind === 'suppl') appendSuppl();
  else appendArts();

  let targetId = null;
  if (s.kind === 'suppl' && supplIdx != null) {
    // 目当ての附則が後ろのほうにあるなら、そこまで描いてから飛ぶ
    while (shown <= supplIdx && shown < curLaw.suppl.length) appendSuppl();
    targetId = highlightNum ? 'sart-' + supplIdx + '-' + highlightNum : 'sblk-' + supplIdx;
  } else if (s.kind === 'main' && highlightNum != null) {
    const target = curLaw.articles.findIndex((a) => a.num === highlightNum);
    while (target >= 0 && s.from + shown <= target && shown < s.to - s.from) appendArts();
    targetId = 'art-' + highlightNum;
  }

  if (targetId) {
    // requestAnimationFrame は裏のタブだと止まるので setTimeout にしておく
    setTimeout(() => {
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ block: 'start' });
        el.classList.add('hl');
        setTimeout(() => el.classList.remove('hl'), 2200);
      }
    });
  } else {
    window.scrollTo({ top: 0 });
  }
}
$('#btn-sec-prev').addEventListener('click', () => { if (curSec > 0) openSection(curSec - 1); });
$('#btn-sec-next').addEventListener('click', () => { if (curSec < sections.length - 1) openSection(curSec + 1); });
$('#btn-law-toc').addEventListener('click', showToc);
$('#btn-law-back').addEventListener('click', () => {
  $('#law-detail-view').classList.add('hidden');
  $('#law-list-view').classList.remove('hidden');
  renderLawGrid();
  window.scrollTo({ top: 0 });
});

function renderPreamble() {
  return `<div class="art preamble"><div class="art-head"><span class="art-k">前文</span></div>
    <div class="art-body">${curLaw.preamble.map((p) => `<p>${esc(p)}</p>`).join('')}</div></div>`;
}

function appendArts() {
  const s = sections[curSec];
  const from = s.from + shown;
  const to = Math.min(s.from + shown + PAGE, s.to);
  // 章立ては上の section-bar に出ているので、条文ごとの所属は繰り返さない
  const html = curLaw.articles.slice(from, to).map((a) => artHtml(curLaw.key, a, { path: false })).join('');
  $('#art-list').insertAdjacentHTML('beforeend', html);
  shown = to - s.from;
  const rest = s.to - s.from - shown;
  const more = $('#btn-art-more');
  more.classList.toggle('hidden', rest <= 0);
  more.textContent = '続きを表示（あと' + rest + '条）';
  bindArtTools($('#art-list'));
}
$('#btn-art-more').addEventListener('click', () => {
  if (sections[curSec] && sections[curSec].kind === 'suppl') appendSuppl();
  else appendArts();
});

/* ========== 附則 ========== */
function appendSuppl() {
  const list = curLaw.suppl;
  const to = Math.min(shown + PAGE_SUPPL, list.length);
  const html = list.slice(shown, to).map((b, k) => supplHtml(b, shown + k)).join('');
  $('#art-list').insertAdjacentHTML('beforeend', html);
  shown = to;
  const rest = list.length - shown;
  const more = $('#btn-art-more');
  more.classList.toggle('hidden', rest <= 0);
  more.textContent = '続きを表示（あと' + rest + '件）';
}

function supplHtml(b, bi) {
  const arts = (b.articles || [])
    .map((a) => artHtml(curLaw.key, a, { path: false, plain: true, id: 'sart-' + bi + '-' + a.num }))
    .join('');
  // 条に分かれていない附則は、項だけをひとかたまりで出す
  const paras = (b.paras || []).length
    ? `<div class="art" id="sart-${bi}-p"><div class="art-body">${
      b.paras.map((p) => paraHtml(p, b.paras.length > 1)).join('')}</div></div>`
    : '';
  return `<section class="suppl-block" id="sblk-${bi}">
    <div class="suppl-head"><span class="suppl-label">${esc(b.label)}</span>
      ${b.num ? `<span class="suppl-num">（${esc(b.num)}）</span>` : ''}
      ${b.extract ? '<span class="suppl-tag" title="必要な条だけを載せた抄録">抄</span>' : ''}</div>
    ${arts}${paras}</section>`;
}

function paraHtml(p, many) {
  const items = (p.items || []).length ? `<ul class="art-items">${(p.items || []).map((it) => `
      <li><span class="ai-t">${esc(it.t)}</span><span>${esc(it.s)}${(it.sub || []).length
        ? `<ul class="art-items">${it.sub.map((s2) => `<li><span class="ai-t">${esc(s2.t)}</span><span>${esc(s2.s)}</span></li>`).join('')}</ul>`
        : ''}</span></li>`).join('')}</ul>` : '';
  const tables = (p.tables || []).map((rows) => `<table class="art-table">${rows.map((r) => `
      <tr>${r.map((c) => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</table>`).join('');
  const n = many ? (CIRCLED[+p.n - 1] || p.n) : '';
  return `<div class="art-para"><span class="art-pnum">${n}</span><div class="art-ptext">
    ${p.cap ? `<div class="art-pcap">${esc(p.cap)}</div>` : ''}${esc(p.s)}${items}${tables}</div></div>`;
}

function artHtml(lawKey, a, opts) {
  const o = opts || {};
  const many = a.paras.length > 1;
  const deleted = a.paras.length === 1 && a.paras[0].s === '削除';
  const body = `<div class="art-body">${a.paras.map((p) => paraHtml(p, many)).join('')}</div>`;
  // 附則の条は本則と条番号がかぶるので、⭐とメモは付けない（保存先の鍵が衝突するため）
  if (o.plain) {
    return `<div class="art${deleted ? ' art-del' : ''}" id="${esc(o.id || ('art-' + a.num))}">
      <div class="art-head"><span class="art-k">${esc(a.k)}</span>
        ${S.set.cap && a.cap ? `<span class="art-cap">${esc(a.cap)}</span>` : ''}</div>
      ${body}</div>`;
  }
  const r = ref(lawKey, a.num);
  const starred = S.savedArts.includes(r);
  const memo = S.memos[r];
  return `<div class="art${deleted ? ' art-del' : ''}" id="art-${esc(a.num)}" data-ref="${esc(r)}">
    <div class="art-head">
      <span class="art-k">${esc(a.k)}</span>
      ${S.set.cap && a.cap ? `<span class="art-cap">${esc(a.cap)}</span>` : ''}
      <span class="art-tools">
        <button class="star${starred ? ' on' : ''}" data-act="star" title="保存">⭐</button>
        <button class="star${memo ? ' on' : ''}" data-act="memo" title="メモ">📝</button>
      </span>
    </div>
    ${o.path !== false && a.path && a.path.length ? `<div class="art-path">${esc(a.path.join(' › '))}</div>` : ''}
    ${body}
    ${o.note ? `<div class="study-note">${esc(o.note)}</div>` : ''}
    ${memo ? `<div class="memo-box">${esc(memo)}</div>` : ''}
  </div>`;
}

function bindArtTools(root) {
  $$('[data-act]', root).forEach((b) => {
    if (b._bound) return;
    b._bound = true;
    b.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const r = b.closest('.art').dataset.ref;
      if (b.dataset.act === 'star') toggleStar(r, b);
      else openMemo(r);
    });
  });
}

function toggleStar(r, btn) {
  const i = S.savedArts.indexOf(r);
  if (i >= 0) { S.savedArts.splice(i, 1); toast('保存をはずしました'); }
  else { S.savedArts.push(r); toast('⭐ 保存しました'); }
  save();
  if (btn) btn.classList.toggle('on', i < 0);
  else refreshArtFlags();
}
function refreshArtFlags() {
  $$('.art').forEach((el) => {
    const r = el.dataset.ref;
    const star = $('[data-act="star"]', el);
    const memo = $('[data-act="memo"]', el);
    if (star) star.classList.toggle('on', S.savedArts.includes(r));
    if (memo) memo.classList.toggle('on', !!S.memos[r]);
  });
}

/* ========== メモ ========== */
let memoRef = null;
function openMemo(r) {
  memoRef = r;
  const [law, num] = r.split(':');
  const a = window.LAWDATA[law] && findArt(window.LAWDATA[law], num);
  $('#memo-title').textContent = (META[law] ? META[law].title : law) + ' ' + (a ? a.k : num);
  $('#memo-text').value = S.memos[r] || '';
  $('#memo-dialog').showModal();
}
$('#memo-dialog').addEventListener('close', () => {
  const dlg = $('#memo-dialog');
  if (!memoRef) return;
  if (dlg.returnValue === 'ok') {
    const v = $('#memo-text').value.trim();
    if (v) S.memos[memoRef] = v; else delete S.memos[memoRef];
    save();
    toast(v ? '📝 メモを保存しました' : 'メモを削除しました');
  } else if (dlg.returnValue === 'del') {
    delete S.memos[memoRef];
    save();
    toast('メモを削除しました');
  } else { memoRef = null; return; }
  const el = $(`.art[data-ref="${CSS.escape(memoRef)}"]`);
  if (el) {
    const box = $('.memo-box', el);
    const txt = S.memos[memoRef];
    if (txt && box) box.textContent = txt;
    else if (txt) el.insertAdjacentHTML('beforeend', `<div class="memo-box">${esc(txt)}</div>`);
    else if (box) box.remove();
  }
  refreshArtFlags();
  if ($('#tab-saved').classList.contains('active')) renderSaved();
  memoRef = null;
});

/* ========================================================
   検索
   ======================================================== */
const sxLaws = new Set();
let sxIndex = null;

function renderSxChips() {
  $('#sx-laws').innerHTML = '<button class="chip' + (sxLaws.size ? '' : ' active') + '" data-l="">すべて</button>'
    + METAS.map((m) => `<button class="chip${sxLaws.has(m.key) ? ' active' : ''}" data-l="${m.key}">${esc(m.short)}</button>`).join('');
  $$('#sx-laws .chip').forEach((c) => c.addEventListener('click', () => {
    const k = c.dataset.l;
    if (!k) sxLaws.clear();
    else if (sxLaws.has(k)) sxLaws.delete(k);
    else sxLaws.add(k);
    renderSxChips();
    runSearch();
  }));
}

function buildIndex(keys) {
  sxIndex = sxIndex || {};
  keys.forEach((k) => {
    if (sxIndex[k]) return;
    const law = window.LAWDATA[k];
    const main = law.articles.map((a) => ({
      a, hay: norm(a.k + ' ' + (a.cap || '') + ' ' + artText(a)), cap: norm(a.k + ' ' + (a.cap || '')),
    }));
    const suppl = [];
    (law.suppl || []).forEach((b, bi) => {
      const head = b.label + ' ' + (b.num || '');
      (b.articles || []).forEach((a) => suppl.push({
        a, bi, head,
        hay: norm(head + ' ' + a.k + ' ' + (a.cap || '') + ' ' + artText(a)),
        cap: norm(head + ' ' + a.k + ' ' + (a.cap || '')),
      }));
      if ((b.paras || []).length) {
        // 条に分かれていない附則は、かたまりごと一件として扱う
        const whole = { k: b.label, num: '', paras: b.paras };
        suppl.push({ a: whole, bi, head, hay: norm(head + ' ' + artText(whole)), cap: norm(head) });
      }
    });
    sxIndex[k] = { main, suppl };
  });
}

let sxTimer = null;
$('#sx-input').addEventListener('input', () => {
  clearTimeout(sxTimer);
  sxTimer = setTimeout(runSearch, 220);
});
$('#sx-cap').addEventListener('change', runSearch);
$('#sx-suppl').addEventListener('change', runSearch);

function runSearch() {
  const q = norm($('#sx-input').value.trim());
  if (q.length < 1) {
    $('#sx-results').innerHTML = '<div class="empty">さがしたい言葉を入れてください。<br>条文の本文からも見出しからも探せます。</div>';
    $('#sx-count').textContent = '';
    return;
  }
  const keys = sxLaws.size ? Array.from(sxLaws) : METAS.map((m) => m.key);
  const missing = keys.filter((k) => !window.LAWDATA[k]);
  if (missing.length) {
    $('#sx-results').innerHTML = '<div class="loading">条文を読み込んでいます… 0 / ' + missing.length + '</div>';
    loadLaws(missing, (d, t) => {
      const el = $('#sx-results .loading');
      if (el) el.textContent = '条文を読み込んでいます… ' + d + ' / ' + t;
    }).then(runSearch).catch(() => { $('#sx-results').innerHTML = '<div class="empty">条文を読み込めませんでした</div>'; });
    return;
  }
  buildIndex(keys);
  const capOnly = $('#sx-cap').checked;
  const withSuppl = $('#sx-suppl').checked;
  const hits = [];
  outer:
  for (const k of keys) {
    // 本則を先に出し、そのあとに附則をまわす
    for (const part of withSuppl ? ['main', 'suppl'] : ['main']) {
      for (const row of sxIndex[k][part]) {
        if ((capOnly ? row.cap : row.hay).includes(q)) hits.push({ k, row });
        if (hits.length >= 400) break outer;
      }
    }
  }
  $('#sx-count').textContent = hits.length >= 400 ? '400件以上（先頭400件）' : hits.length + '件';
  $('#sx-results').innerHTML = hits.length
    ? hits.map((h) => hitHtml(h.k, h.row, q)).join('')
    : '<div class="empty">見つかりませんでした</div>';
  $$('#sx-results .hit').forEach((el) => el.addEventListener('click', () => {
    goTab('laws');
    const sup = el.dataset.sup;
    openLaw(el.dataset.law, sup ? { suppl: +sup, num: el.dataset.num || null } : { num: el.dataset.num });
  }));
}

function snippet(a, q) {
  const text = artText(a).replace(/\n/g, ' ');
  const at = norm(text).indexOf(q);
  if (at < 0) return text.slice(0, 110) + (text.length > 110 ? '…' : '');
  const from = Math.max(0, at - 30);
  const cut = text.slice(from, at + q.length + 80);
  return (from ? '…' : '') + cut + (at + q.length + 80 < text.length ? '…' : '');
}
function markup(text, q) {
  const n = norm(text);
  let out = '', at = 0;
  for (;;) {
    const i = n.indexOf(q, at);
    if (i < 0 || !q) { out += esc(text.slice(at)); break; }
    out += esc(text.slice(at, i)) + '<mark>' + esc(text.slice(i, i + q.length)) + '</mark>';
    at = i + q.length;
  }
  return out;
}
function hitHtml(k, row, q) {
  const m = META[k];
  const a = row.a;
  const sup = row.bi != null;
  return `<div class="hit" style="--ec:${m.color}" data-law="${k}" data-num="${esc(a.num)}"${
    sup ? ` data-sup="${row.bi}"` : ''}>
    <div class="hit-head"><span class="hit-law">${esc(m.short)}</span>
      ${sup ? '<span class="hit-sup">附則</span>' : ''}
      <span class="hit-k">${esc(a.k)}</span>
      ${a.cap ? `<span class="hit-cap">${markup(a.cap, q)}</span>` : ''}</div>
    ${sup ? `<div class="art-path">${esc(row.head)}</div>` : ''}
    <div class="hit-body">${markup(snippet(a, q), q)}</div></div>`;
}

/* ========================================================
   条文ジャンプ
   ======================================================== */
$('#btn-jump').addEventListener('click', () => {
  $('#jp-input').value = '';
  $('#jp-results').innerHTML = '';
  $('#jump-dialog').showModal();
  setTimeout(() => $('#jp-input').focus(), 30);
});
$('#jp-close').addEventListener('click', () => $('#jump-dialog').close());

function parseJump(raw) {
  const s = raw.replace(/[\s　]/g, '').normalize('NFKC');
  let lawKey = null, rest = s;
  for (const m of METAS) {
    for (const name of [m.title, m.short, m.kana]) {
      if (name && s.startsWith(name)) { lawKey = m.key; rest = s.slice(name.length); break; }
    }
    if (lawKey) break;
  }
  rest = rest.replace(/^第/, '').replace(/条$/, '');
  const num = rest.replace(/の/g, '_').replace(/[^0-9_]/g, '');
  return { lawKey: lawKey || S.lastLaw, num, rest };
}

$('#jp-input').addEventListener('input', () => {
  const raw = $('#jp-input').value.trim();
  if (!raw) { $('#jp-results').innerHTML = ''; return; }
  const { lawKey, num, rest } = parseJump(raw);
  const m = META[lawKey];
  if (!num) {
    $('#jp-results').innerHTML = `<div class="sd-item"><div class="sd-meta">${esc(m.title)}</div>
      <div class="sd-d">続けて条番号を入れてください（例：${esc(m.short)}1）</div></div>`;
    return;
  }
  $('#jp-results').innerHTML = '<div class="loading">さがしています…</div>';
  loadLaw(lawKey).then((law) => {
    if ($('#jp-input').value.trim() !== raw) return;   // 入力が進んでいたらやめる
    const head = num.split('_')[0];
    const cands = law.articles.filter((a) => {
      if (a.num === num) return true;
      if (a.sk[0] === +head && String(a.num).startsWith(head)) return true;
      if (a.r && +head >= a.r[0] && +head <= a.r[1]) return true;
      return false;
    }).slice(0, 12);
    $('#jp-results').innerHTML = cands.length ? cands.map((a) => `
      <div class="sd-item" data-num="${esc(a.num)}">
        <div class="sd-w">${esc(a.k)}${a.cap ? ' ' + esc(a.cap) : ''}</div>
        <div class="sd-meta">${esc(m.title)}</div>
        <div class="sd-d">${esc(artText(a).replace(/\n/g, ' ').slice(0, 70))}…</div>
      </div>`).join('') : `<div class="empty">${esc(m.title)}に 第${esc(rest)}条 は見つかりませんでした</div>`;
    $$('#jp-results .sd-item[data-num]').forEach((el) => el.addEventListener('click', () => {
      $('#jump-dialog').close();
      goTab('laws');
      openLaw(lawKey, { num: el.dataset.num });
    }));
  }).catch(() => { $('#jp-results').innerHTML = '<div class="empty">条文を読み込めませんでした</div>'; });
});

/* ========================================================
   重要条文
   ======================================================== */
const GROUPS = window.STUDY.groups;
let studyLaw = '';
let curGroup = null;

function renderStudyChips() {
  const used = METAS.filter((m) => GROUPS.some((g) => g.law === m.key));
  $('#study-law-chips').innerHTML = '<button class="chip' + (studyLaw ? '' : ' active') + '" data-l="">すべて</button>'
    + used.map((m) => `<button class="chip${studyLaw === m.key ? ' active' : ''}" data-l="${m.key}">${esc(m.short)}</button>`).join('');
  $$('#study-law-chips .chip').forEach((c) => c.addEventListener('click', () => {
    studyLaw = c.dataset.l === studyLaw ? '' : c.dataset.l;
    renderStudyChips();
    renderStudyGrid();
  }));
}
function studyList() { return studyLaw ? GROUPS.filter((g) => g.law === studyLaw) : GROUPS; }

function renderStudyGrid() {
  const list = studyList();
  $('#study-grid').innerHTML = list.map((g) => {
    const m = META[g.law];
    return `<button class="era-card" style="--ec:${m.color}" data-g="${g.id}">
      ${S.read[g.id] ? '<span class="ec-badge">読了</span>' : ''}
      <div class="ec-top"><span class="ec-icon">${g.icon}</span>
        <div><div class="ec-name">${esc(g.name)}</div>
        <div class="ec-span">${esc(m.title)}・${g.arts.length}条</div></div></div>
      <div class="ec-catch">${esc(g.desc)}</div>
    </button>`;
  }).join('');
  $$('#study-grid .era-card').forEach((b) => b.addEventListener('click', () => openGroup(b.dataset.g)));
}

function openGroup(id) {
  const g = GROUPS.find((x) => x.id === id);
  if (!g) return;
  curGroup = g;
  const m = META[g.law];
  $('#study-list-view').classList.add('hidden');
  $('#study-detail-view').classList.remove('hidden');
  $('#study-hero').style.setProperty('--ec', m.color);
  $('#study-hero').innerHTML = `
    <div class="lc-top"><span class="lh-icon">${g.icon}</span>
      <div><h2>${esc(g.name)}</h2><div class="lh-kana">${esc(m.title)}</div></div></div>
    <div class="lh-blurb">${esc(g.desc)}</div>`;
  $('#study-body').innerHTML = '<div class="loading">条文を読み込んでいます…</div>';
  if (!S.read[id]) { S.read[id] = true; save(); }
  window.scrollTo({ top: 0 });
  loadLaw(g.law).then((law) => {
    if (curGroup !== g) return;
    $('#study-body').innerHTML = g.arts.map((rf) => {
      const a = findArt(law, rf.n);
      if (!a) return '';
      return artHtml(g.law, a, { note: rf.note, path: false });
    }).join('');
    bindArtTools($('#study-body'));
  }).catch(() => { $('#study-body').innerHTML = '<div class="empty">条文を読み込めませんでした</div>'; });
}
$('#btn-study-back').addEventListener('click', () => {
  $('#study-detail-view').classList.add('hidden');
  $('#study-list-view').classList.remove('hidden');
  renderStudyGrid();
  window.scrollTo({ top: 0 });
});
function stepGroup(d) {
  const list = studyList();
  const i = list.findIndex((g) => g === curGroup);
  openGroup(list[(i + d + list.length) % list.length].id);
}
$('#btn-study-prev').addEventListener('click', () => stepGroup(-1));
$('#btn-study-next').addEventListener('click', () => stepGroup(1));
$('#btn-study-quiz').addEventListener('click', () => {
  if (!curGroup) return;
  qLaws.clear();
  qLaws.add(curGroup.law);
  quizGroupOnly = curGroup.id;
  renderQLawChips();
  goTab('quiz');
  startQuiz();
});

/* ========================================================
   用語
   ======================================================== */
const TERMS = window.STUDY.terms;
let tmLaw = '';
function renderTermChips() {
  const used = METAS.filter((m) => TERMS.some((t) => t.law === m.key));
  $('#tm-chips').innerHTML = '<button class="chip' + (tmLaw ? '' : ' active') + '" data-l="">すべて</button>'
    + used.map((m) => `<button class="chip${tmLaw === m.key ? ' active' : ''}" data-l="${m.key}">${esc(m.short)}</button>`).join('');
  $$('#tm-chips .chip').forEach((c) => c.addEventListener('click', () => {
    tmLaw = c.dataset.l === tmLaw ? '' : c.dataset.l;
    renderTermChips();
    renderTerms();
  }));
}
function renderTerms() {
  const q = norm($('#tm-input').value.trim());
  const list = TERMS.filter((t) => (!tmLaw || t.law === tmLaw)
    && (!q || norm(t.w + t.y + t.d).includes(q)));
  $('#tm-list').innerHTML = list.length ? list.map((t) => `
    <div class="kw"><div class="kw-main">
      <div><span class="kw-w">${esc(t.w)}</span><span class="kw-y">${esc(t.y)}</span>
        <span class="kw-y">${esc(META[t.law] ? META[t.law].short : '')}</span></div>
      <div class="kw-d">${esc(t.d)}</div>
    </div></div>`).join('') : '<div class="empty">見つかりませんでした</div>';
}
$('#tm-input').addEventListener('input', renderTerms);

/* ========================================================
   クイズ
   ======================================================== */
const TYPES = {
  note: '説明から条文をあてる',
  cap: '見出しから条文をあてる',
  blank: '条文の穴埋め',
  law: '条文がどの法律かあてる',
  num: '条番号から条文をあてる',
};
const TYPE_NOTE = {
  note: 'ひとこと解説を読んで、どの条文のことか選びます。どの法律でも出ます。',
  cap: '（不法行為による損害賠償）のような見出しから条番号を選びます。見出しのある法律だけ。',
  blank: '条文の一部が空欄になっています。あてはまる言葉を選びます。',
  law: '条文を読んで、どの法律の条文か選びます。',
  num: '条番号を見て、その中身を選びます。',
};
const qLaws = new Set();
const qTypes = new Set(['note', 'blank', 'law', 'cap']);
let quizGroupOnly = null;
let quiz = [], qi = 0, qCorrect = 0, answered = false;

function renderQLawChips() {
  const used = METAS.filter((m) => GROUPS.some((g) => g.law === m.key));
  $('#q-law-chips').innerHTML = '<button class="chip' + (qLaws.size ? '' : ' active') + '" data-l="">すべて</button>'
    + used.map((m) => `<button class="chip${qLaws.has(m.key) ? ' active' : ''}" data-l="${m.key}">${esc(m.short)}</button>`).join('');
  $$('#q-law-chips .chip').forEach((c) => c.addEventListener('click', () => {
    const k = c.dataset.l;
    quizGroupOnly = null;
    if (!k) qLaws.clear();
    else if (qLaws.has(k)) qLaws.delete(k);
    else qLaws.add(k);
    renderQLawChips();
    updatePool();
  }));
}
function renderQTypeChips() {
  $('#q-type-chips').innerHTML = Object.keys(TYPES)
    .map((t) => `<button class="chip${qTypes.has(t) ? ' active' : ''}" data-t="${t}">${esc(TYPES[t])}</button>`).join('');
  $$('#q-type-chips .chip').forEach((c) => c.addEventListener('click', () => {
    const t = c.dataset.t;
    if (qTypes.has(t)) { if (qTypes.size > 1) qTypes.delete(t); } else qTypes.add(t);
    renderQTypeChips();
    updatePool();
  }));
  $('#type-notes').innerHTML = Object.keys(TYPES)
    .map((t) => `<li><b>${esc(TYPES[t])}</b> — ${esc(TYPE_NOTE[t])}</li>`).join('');
}

function quizGroups() {
  if (quizGroupOnly) return GROUPS.filter((g) => g.id === quizGroupOnly);
  return qLaws.size ? GROUPS.filter((g) => qLaws.has(g.law)) : GROUPS;
}
function updatePool() {
  const gs = quizGroups();
  const arts = gs.reduce((n, g) => n + g.arts.length, 0);
  $('#q-pool').textContent = `対象 ${gs.length}分野・${arts}条`;
}

/* 条文中に出てくる穴埋め候補のうち、いちばん長いものを選ぶ */
const BLANKS = window.STUDY.blanks.slice().sort((a, b) => b.length - a.length);
function pickBlank(text) {
  for (const w of BLANKS) {
    const at = text.indexOf(w);
    if (at >= 0 && w.length >= 2) return { w, at };
  }
  return null;
}

function buildQuestions() {
  const gs = quizGroups();
  const out = [];
  gs.forEach((g) => {
    const law = window.LAWDATA[g.law];
    if (!law) return;
    const sameLaw = g.arts.map((rf) => findArt(law, rf.n)).filter(Boolean);
    g.arts.forEach((rf) => {
      const a = findArt(law, rf.n);
      if (!a) return;
      const text = artText(a).replace(/\n/g, ' ');
      if (text === '削除') return;
      const base = { law: g.law, group: g.id, num: a.num, art: a, note: rf.note };

      // 解説が見出しの言い換えにすぎないものは、「見出しから」と同じ問題になるので出さない
      const noteIsCap = a.cap && rf.note
        && rf.note.replace(/[。（）()]/g, '') === a.cap.replace(/[。（）()]/g, '');
      if (qTypes.has('note') && rf.note && !noteIsCap) {
        const others = sample(sameLaw.filter((x) => x !== a), 3);
        if (others.length === 3) {
          out.push(Object.assign({}, base, {
            type: 'note',
            q: `次の説明にあてはまるのは、${META[g.law].title}の何条でしょう。\n\n「${rf.note}」`,
            choices: [a].concat(others).map((x) => x.k),
            answer: a.k,
          }));
        }
      }
      if (qTypes.has('cap') && a.cap) {
        const others = sample(sameLaw.filter((x) => x !== a && x.cap), 3);
        if (others.length === 3) {
          out.push(Object.assign({}, base, {
            type: 'cap',
            q: `${META[g.law].title}で、見出しが ${a.cap} の条文はどれでしょう。`,
            choices: [a].concat(others).map((x) => x.k),
            answer: a.k,
          }));
        }
      }
      if (qTypes.has('blank')) {
        const b = pickBlank(text);
        if (b) {
          const others = sample(BLANKS.filter((w) => w !== b.w && !text.includes(w)
            && Math.abs(w.length - b.w.length) <= 4), 3);
          if (others.length === 3) {
            const shown = text.length > 180 ? clipAround(text, b.at, b.w.length, 180) : { t: text, at: b.at };
            out.push(Object.assign({}, base, {
              type: 'blank',
              q: `${META[g.law].title} ${a.k}${a.cap ? ' ' + a.cap : ''}\n\n`
                + shown.t.slice(0, shown.at) + '〔　？　〕' + shown.t.slice(shown.at + b.w.length),
              choices: [b.w].concat(others),
              answer: b.w,
            }));
          }
        }
      }
      if (qTypes.has('law')) {
        const others = sample(METAS.filter((m) => m.key !== g.law), 3);
        out.push(Object.assign({}, base, {
          type: 'law',
          q: '次の条文は、どの法律のものでしょう。\n\n「' + text.slice(0, 130) + (text.length > 130 ? '…' : '') + '」',
          choices: [META[g.law].title].concat(others.map((m) => m.title)),
          answer: META[g.law].title,
        }));
      }
      if (qTypes.has('num')) {
        const others = sample(sameLaw.filter((x) => x !== a), 3);
        if (others.length === 3) {
          const cut = (x) => { const t = artText(x).replace(/\n/g, ' '); return t.slice(0, 60) + (t.length > 60 ? '…' : ''); };
          out.push(Object.assign({}, base, {
            type: 'num',
            q: `${META[g.law].title} ${a.k} の内容はどれでしょう。`,
            choices: [cut(a)].concat(others.map(cut)),
            answer: cut(a),
          }));
        }
      }
    });
  });
  out.forEach((q) => { q.id = q.law + ':' + q.num + ':' + q.type; });
  return out;
}

function clipAround(text, at, len, width) {
  const from = Math.max(0, Math.min(at - Math.floor((width - len) / 2), text.length - width));
  return { t: (from ? '…' : '') + text.slice(from, from + width) + (from + width < text.length ? '…' : ''),
    at: at - from + (from ? 1 : 0) };
}

$('#btn-quiz-start').addEventListener('click', startQuiz);
function startQuiz() {
  const keys = Array.from(new Set(quizGroups().map((g) => g.law)));
  const missing = keys.filter((k) => !window.LAWDATA[k]);
  $('#btn-quiz-start').disabled = true;
  loadLaws(missing).then(() => {
    $('#btn-quiz-start').disabled = false;
    let all = buildQuestions();
    if (!all.length) { toast('出題できる問題がありません'); return; }
    if ($('#q-weak').checked) {
      all.sort((a, b) => missRate(b.id) - missRate(a.id));
      const n = +$('#q-count').value || all.length;
      all = shuffle(all.slice(0, Math.max(n * 2, n)));
    } else {
      all = shuffle(all);
    }
    const n = +$('#q-count').value;
    quiz = n ? all.slice(0, n) : all;
    qi = 0; qCorrect = 0;
    $('#quiz-setup').classList.add('hidden');
    $('#quiz-result').classList.add('hidden');
    $('#quiz-play').classList.remove('hidden');
    showQuestion();
    window.scrollTo({ top: 0 });
  }).catch(() => {
    $('#btn-quiz-start').disabled = false;
    toast('条文を読み込めませんでした');
  });
}
function missRate(id) {
  const st = S.qstat[id];
  if (!st || !st.o) return 0.5;        // まだ解いていない問題は真ん中あつかい
  return st.x / st.o;
}
$('#btn-quiz-quit').addEventListener('click', () => {
  $('#quiz-play').classList.add('hidden');
  $('#quiz-setup').classList.remove('hidden');
  quizGroupOnly = null;
  updatePool();
});

function showQuestion() {
  answered = false;
  const q = quiz[qi];
  const m = META[q.law];
  $('#q-progress').textContent = (qi + 1) + ' / ' + quiz.length;
  $('#q-bar').style.width = (qi / quiz.length * 100) + '%';
  $('#btn-q-next').classList.add('hidden');
  setSaveLabel(S.savedQuiz.includes(q.id));
  const choices = S.set.shuffle ? shuffle(q.choices) : q.choices;
  q._shown = choices;
  const body = q.type === 'blank'
    ? `<div class="q-src">${esc(q.q).replace(/〔　？　〕/, '<span class="q-blank">？</span>')}</div>`
    : `<div class="q-text">${esc(q.q)}</div>`;
  $('#q-area').innerHTML = `
    <div class="q-meta">
      <span class="q-tag era">${esc(m.short)}</span>
      <span class="q-tag">${esc(TYPES[q.type])}</span>
    </div>
    ${body}
    <div class="choices">${choices.map((c, i) => `
      <button class="choice" data-i="${i}"><span class="num">${i + 1}</span><span>${esc(c)}</span></button>`).join('')}</div>
    <div id="q-after"></div>`;
  $$('#q-area .choice').forEach((b) => b.addEventListener('click', () => answer(+b.dataset.i)));
}

function answer(i) {
  if (answered) return;
  answered = true;
  const q = quiz[qi];
  const picked = q._shown[i];
  const ok = picked === q.answer;
  $$('#q-area .choice').forEach((b, j) => {
    b.disabled = true;
    if (q._shown[j] === q.answer) b.classList.add('correct');
    else if (j === i) b.classList.add('wrong');
  });

  const st = S.qstat[q.id] || { o: 0, x: 0 };
  st.o += 1;
  if (!ok) st.x += 1;
  S.qstat[q.id] = st;
  const ls = S.lawstat[q.law] || { o: 0, c: 0 };
  ls.o += 1; if (ok) ls.c += 1;
  S.lawstat[q.law] = ls;
  const gs = S.groupstat[q.group] || { o: 0, c: 0 };
  gs.o += 1; if (ok) gs.c += 1;
  S.groupstat[q.group] = gs;
  S.days[today()] = (S.days[today()] || 0) + 1;
  if (ok) qCorrect += 1;
  save();

  const text = artText(q.art).replace(/\n/g, '\n');
  $('#q-after').innerHTML = `
    <div class="verdict ${ok ? 'ok' : 'ng'}">${ok ? '◯ 正解' : '✕ まちがい'}</div>
    <div class="exp">
      <div class="exp-h">${esc(META[q.law].title)} ${esc(q.art.k)}${q.art.cap ? ' ' + esc(q.art.cap) : ''}</div>
      <div style="white-space:pre-wrap;margin-top:6px">${esc(text)}</div>
      ${q.note ? `<div class="study-note">${esc(q.note)}</div>` : ''}
      <div class="row" style="margin-top:10px">
        <button class="btn ghost" id="btn-q-goto">📚 この条文を開く</button><span class="spacer"></span>
      </div>
    </div>`;
  $('#btn-q-goto').addEventListener('click', () => {
    goTab('laws');
    openLaw(q.law, { num: q.num });
  });
  $('#btn-q-next').classList.remove('hidden');
  $('#btn-q-next').textContent = qi + 1 >= quiz.length ? '結果を見る →' : '次の問題 →';
}

$('#btn-q-next').addEventListener('click', () => {
  qi += 1;
  if (qi >= quiz.length) finishQuiz();
  else { showQuestion(); window.scrollTo({ top: 0 }); }
});
function setSaveLabel(on) {
  $('#btn-q-save').textContent = on ? '⭐ 保存ずみ（はずす）' : '⭐ この問題を保存';
}
$('#btn-q-save').addEventListener('click', () => {
  const id = quiz[qi].id;
  const i = S.savedQuiz.indexOf(id);
  if (i >= 0) { S.savedQuiz.splice(i, 1); toast('保存をはずしました'); }
  else { S.savedQuiz.push(id); toast('⭐ 保存しました'); }
  save();
  setSaveLabel(i < 0);
});

function finishQuiz() {
  S.sessions.push({ d: today(), n: quiz.length, c: qCorrect });
  if (S.sessions.length > 200) S.sessions = S.sessions.slice(-200);
  save();
  const p = pct(qCorrect, quiz.length);
  const msg = p === 100 ? '全問正解です。' : p >= 80 ? 'よく読めています。' : p >= 50 ? 'あと少しです。' : '条文に戻って読み直しましょう。';
  $('#quiz-play').classList.add('hidden');
  $('#quiz-result').classList.remove('hidden');
  const wrong = quiz.filter((q) => {
    const st = S.qstat[q.id];
    return st && st.x > 0;
  });
  $('#quiz-result').innerHTML = `
    <div class="card"><div class="result-score">
      <div class="rs-num">${qCorrect} / ${quiz.length}</div>
      <div class="rs-sub">正答率 ${p}%</div>
      <div class="rs-msg">${msg}</div>
    </div></div>
    <div class="card"><strong>この回で出た条文</strong>
      <ul class="list compact">${quiz.map((q) => `
        <li data-law="${q.law}" data-num="${esc(q.num)}">
          <span>${esc(META[q.law].short)} ${esc(q.art.k)}${q.art.cap ? ' ' + esc(q.art.cap) : ''}</span>
        </li>`).join('')}</ul></div>
    <div class="row">
      <button class="btn ghost" id="btn-res-again">↻ もう一度</button><span class="spacer"></span>
      <button class="btn primary" id="btn-res-back">設定へ戻る</button></div>`;
  $$('#quiz-result .list li').forEach((li) => li.addEventListener('click', () => {
    goTab('laws');
    openLaw(li.dataset.law, { num: li.dataset.num });
  }));
  $('#btn-res-again').addEventListener('click', startQuiz);
  $('#btn-res-back').addEventListener('click', () => {
    $('#quiz-result').classList.add('hidden');
    $('#quiz-setup').classList.remove('hidden');
    quizGroupOnly = null;
    updatePool();
  });
  window.scrollTo({ top: 0 });
}

/* ========================================================
   記録
   ======================================================== */
function streak() {
  let n = 0;
  const d = new Date();
  for (;;) {
    const k = d.toISOString().slice(0, 10);
    if (!S.days[k]) { if (n === 0 && k === today()) { d.setDate(d.getDate() - 1); continue; } break; }
    n += 1;
    d.setDate(d.getDate() - 1);
  }
  return n;
}
function renderStats() {
  const o = Object.values(S.lawstat).reduce((s, x) => s + x.o, 0);
  const c = Object.values(S.lawstat).reduce((s, x) => s + x.c, 0);
  $('#stat-tiles').innerHTML = [
    ['解いた問題', o + '問'],
    ['正答率', pct(c, o) + '%'],
    ['連続学習', streak() + '日'],
    ['読んだ分野', Object.keys(S.read).length + ' / ' + GROUPS.length],
    ['保存した条文', S.savedArts.length + '条'],
    ['書いたメモ', Object.keys(S.memos).length + '件'],
  ].map(([k, v]) => `<div class="tile"><div class="tv">${esc(v)}</div><div class="tk">${esc(k)}</div></div>`).join('');

  const bar = (label, st) => `<div class="bar-row"><span class="bl">${esc(label)}</span>
    <div class="bar-track"><div style="width:${pct(st.c, st.o)}%"></div></div>
    <span class="bn">${st.c}/${st.o}</span></div>`;
  const laws = METAS.filter((m) => S.lawstat[m.key]);
  $('#stat-law').innerHTML = laws.length
    ? laws.map((m) => bar(m.short, S.lawstat[m.key])).join('')
    : '<p class="muted small">まだ記録がありません。</p>';
  const gs = GROUPS.filter((g) => S.groupstat[g.id]);
  $('#stat-group').innerHTML = gs.length
    ? gs.map((g) => bar(g.name, S.groupstat[g.id])).join('')
    : '<p class="muted small">まだ記録がありません。</p>';

  $('#stat-read').innerHTML = GROUPS.map((g) =>
    `<span class="read-pill${S.read[g.id] ? ' on' : ''}">${esc(g.name)}</span>`).join('');

  const weak = Object.keys(S.qstat)
    .map((id) => ({ id, st: S.qstat[id] }))
    .filter((x) => x.st.x > 0)
    .sort((a, b) => (b.st.x - a.st.x) || (missRate(b.id) - missRate(a.id)))
    .slice(0, 10);
  $('#stat-weak').innerHTML = weak.length ? weak.map((x) => {
    const [law, num, type] = x.id.split(':');
    const m = META[law];
    return `<li data-law="${law}" data-num="${esc(num)}">
      <span>${esc(m ? m.short : law)} 第${esc(num.replace(/_/g, 'の'))}条 <span class="muted small">${esc(TYPES[type] || '')}</span></span>
      <span class="spacer"></span><span class="miss">${x.st.x}/${x.st.o} ミス</span></li>`;
  }).join('') : '<li class="muted small">まだまちがえた問題はありません。</li>';
  $$('#stat-weak li[data-law]').forEach((li) => li.addEventListener('click', () => {
    goTab('laws');
    openLaw(li.dataset.law, { num: li.dataset.num });
  }));
}
$('#btn-reset-stats').addEventListener('click', () => {
  if (!confirm('クイズの記録と「読んだ分野」を消します。保存した条文とメモは残ります。よろしいですか？')) return;
  S.read = {}; S.qstat = {}; S.lawstat = {}; S.groupstat = {}; S.sessions = []; S.days = {};
  save();
  renderStats();
  toast('学習記録をリセットしました');
});

/* ========================================================
   保存
   ======================================================== */
let savedTab = 'art';
$$('.savedtab').forEach((b) => b.addEventListener('click', () => {
  savedTab = b.dataset.sv;
  $$('.savedtab').forEach((x) => x.classList.toggle('active', x === b));
  renderSaved();
}));

function renderSaved() {
  const area = $('#saved-area');
  if (savedTab === 'quiz') {
    const ids = S.savedQuiz;
    area.innerHTML = ids.length ? ids.map((id) => {
      const [law, num, type] = id.split(':');
      const m = META[law];
      return `<div class="hit" style="--ec:${m ? m.color : ''}" data-law="${law}" data-num="${esc(num)}">
        <div class="hit-head"><span class="hit-law">${esc(m ? m.short : law)}</span>
          <span class="hit-k">第${esc(num.replace(/_/g, 'の'))}条</span>
          <span class="hit-cap">${esc(TYPES[type] || '')}</span></div></div>`;
    }).join('') : '<div class="empty">保存した問題はありません。<br>クイズ中の「⭐ この問題を保存」で貯まります。</div>';
    bindSavedJump(area);
    return;
  }
  const refs = savedTab === 'art' ? S.savedArts : Object.keys(S.memos);
  if (!refs.length) {
    area.innerHTML = savedTab === 'art'
      ? '<div class="empty">保存した条文はありません。<br>条文の ⭐ を押すと、ここに集まります。</div>'
      : '<div class="empty">メモはありません。<br>条文の 📝 から書けます。</div>';
    return;
  }
  area.innerHTML = '<div class="loading">条文を読み込んでいます…</div>';
  const keys = Array.from(new Set(refs.map((r) => r.split(':')[0]))).filter((k) => META[k]);
  loadLaws(keys).then(() => {
    const html = refs.map((r) => {
      const [law, num] = r.split(':');
      const d = window.LAWDATA[law];
      const a = d && findArt(d, num);
      if (!a) return '';
      return artHtml(law, a, { path: false });
    }).join('');
    area.innerHTML = html || '<div class="empty">条文が見つかりませんでした</div>';
    bindArtTools(area);
  }).catch(() => { area.innerHTML = '<div class="empty">条文を読み込めませんでした</div>'; });
}
function bindSavedJump(area) {
  $$('.hit[data-law]', area).forEach((el) => el.addEventListener('click', () => {
    goTab('laws');
    openLaw(el.dataset.law, { num: el.dataset.num });
  }));
}

/* ========================================================
   設定
   ======================================================== */
$('#btn-settings').addEventListener('click', () => $('#settings-dialog').showModal());
function applySet() {
  document.documentElement.style.setProperty('--fs', S.set.fontsize + 'px');
  document.documentElement.setAttribute('data-theme', S.set.theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', S.set.theme === 'dark' ? '#212a44' : '#35497e');
}
$('#set-shuffle').addEventListener('change', (e) => { S.set.shuffle = e.target.checked; save(); });
$('#set-cap').addEventListener('change', (e) => {
  S.set.cap = e.target.checked;
  save();
  if (curSec >= 0 && !$('#law-arts-view').classList.contains('hidden')) openSection(curSec);
});
$('#set-fontsize').addEventListener('change', (e) => { S.set.fontsize = +e.target.value; save(); applySet(); });
$('#set-theme').addEventListener('change', (e) => { S.set.theme = e.target.value; save(); applySet(); });

/* ========================================================
   起動
   ======================================================== */
$('#set-shuffle').checked = S.set.shuffle;
$('#set-cap').checked = S.set.cap;
$('#set-fontsize').value = String(S.set.fontsize);
$('#set-theme').value = S.set.theme;
$('#set-about').textContent =
  `条文は ${INDEX.source} から取得した ${INDEX.built} 時点のデータです。`
  + '官報の内容と異なる場合は官報が優先します。正確さを保証するものではないので、'
  + '実際の手続や判断にあたっては原典をお確かめください。'
  + '学習記録・保存した条文・メモは、この端末のブラウザ内にのみ保存されます。';
applySet();

renderLawGrid();
renderSxChips();
runSearch();
renderStudyChips();
renderStudyGrid();
renderTermChips();
renderTerms();
renderQLawChips();
renderQTypeChips();
updatePool();

/* ========== オフライン保存 ========== */
$('#set-offline').addEventListener('click', async () => {
  const btn = $('#set-offline');
  const note = $('#set-offline-note');
  if (!('caches' in window) || !navigator.serviceWorker || !navigator.serviceWorker.controller) {
    note.textContent = 'この環境ではオフライン保存が使えません。https:// で開いているか確かめてください。';
    return;
  }
  const files = METAS.map((m) => 'laws/' + m.key + '.js?v=4');
  btn.disabled = true;
  let done = 0;
  try {
    for (const url of files) {
      // Service Worker が横から受け取ってキャッシュに入れてくれる
      await fetch(url, { cache: 'reload' });
      done += 1;
      note.textContent = `保存中… ${done} / ${files.length}`;
    }
    note.textContent = `${files.length}件の法令を保存しました。電波がなくても全部読めます。`;
    toast('⬇ オフライン保存が終わりました');
  } catch (e) {
    note.textContent = `途中で止まりました（${done} / ${files.length}）。通信を確かめてもう一度お試しください。`;
  }
  btn.disabled = false;
});

/* ========== 新しい版のお知らせ ========== */
function watchForUpdate(reg) {
  const offer = (worker) => {
    $('#update-bar').classList.remove('hidden');
    $('#btn-update').onclick = () => {
      $('#btn-update').disabled = true;
      $('#btn-update').textContent = '更新中…';
      worker.postMessage('SKIP_WAITING');
    };
  };
  if (reg.waiting && navigator.serviceWorker.controller) offer(reg.waiting);
  reg.addEventListener('updatefound', () => {
    const w = reg.installing;
    if (!w) return;
    w.addEventListener('statechange', () => {
      // controller があるのは2回目以降の訪問。初回は黙って入れておく。
      if (w.state === 'installed' && navigator.serviceWorker.controller) offer(w);
    });
  });
}

if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
  let reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (reloading) return;
    reloading = true;
    location.reload();
  });
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').then(watchForUpdate).catch(() => {});
  });
}
