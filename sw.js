// オフライン対応: アプリのファイルはネット優先で取得し、つながらないときはキャッシュを使う
// ファイルを更新したら CACHE の番号と、index.html の ?v= の番号を一緒に上げる
//
// laws/*.js は合わせて3.6MBあるので、最初から全部キャッシュはしない。
// 一度開いた法令だけが下の fetch ハンドラでキャッシュに入っていく。
const CACHE = 'roppo-v4';
const FILES = [
  './',
  'index.html',
  'style.css',
  'app.js',
  'data-study.js',
  'laws/index.js',
  'manifest.webmanifest',
  'icon-192.png',
  'icon-512.png',
  'icon-maskable-512.png',
  'apple-touch-icon.png',
];

// 新しい版をすぐには適用しない。利用者が「更新する」を押したときに入れ替える。
// （読んでいる途中で中身がすり替わるのを避けるため）
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(FILES.map((f) => new Request(f, { cache: 'reload' })))),
  );
});

self.addEventListener('message', (e) => {
  if (e.data === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  const fresh = req.mode === 'navigate' ? fetch(req.url, { cache: 'no-cache' }) : fetch(req, { cache: 'no-cache' });
  e.respondWith(
    fresh
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }).then((r) => r || caches.match('index.html'))),
  );
});
