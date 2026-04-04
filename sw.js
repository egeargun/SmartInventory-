/**
 * Akıllı Envanter V2 — Production Service Worker
 * Strateji: Network-First (API istekleri) + Cache-First (statik varlıklar)
 * Cache versiyonunu her deploy'da artır → eski cache otomatik temizlenir.
 */

const CACHE_VERSION = 'v4';
const STATIC_CACHE = `inventory-static-${CACHE_VERSION}`;
const API_CACHE    = `inventory-api-${CACHE_VERSION}`;

// Offline'da da erişilebilir olmasını istediğimiz statik dosyalar
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/kasa.html',
  '/manifest.json',
  '/sw.js',
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://unpkg.com/html5-qrcode',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap'
];

// API endpoint'leri — bunlar network-first olmalı, fresh data önemli
const API_ROUTES = [
  '/dashboard-ozet',
  '/urunler',
  '/sevk-raporu',
  '/ai-predictor',
  '/audit-logs',
  '/bekleyen-talepler',
  '/tedarikci-siparis',
  '/skt-analizi',
  '/fire-raporu',
  '/menu-getir',
  '/kasa-menu-katmanli',
  '/masa-liste',
  '/talep-tahmini',
  '/api/v1/api-keys'
];

// ============================================================
// INSTALL: Statik varlıkları önceden cache'le
// ============================================================
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS.filter(u => !u.startsWith('http'))))
      .then(() => self.skipWaiting())  // Aktif SW'yi hemen geçersiz kıl
  );
});

// ============================================================
// ACTIVATE: Eski versiyonlardaki cache'leri temizle
// ============================================================
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(name => name !== STATIC_CACHE && name !== API_CACHE)
          .map(name => {
            console.log(`[SW] Eski cache siliniyor: ${name}`);
            return caches.delete(name);
          })
      );
    }).then(() => self.clients.claim())  // Tüm tab'ları hemen kontrol et
  );
});

// ============================================================
// FETCH: Akıllı istek yöneticisi
// ============================================================
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // POST/PUT/DELETE gibi mutasyonları asla cache'leme
  if (request.method !== 'GET') return;

  // WebSocket bağlantılarını es geç
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return;

  // Token endpoint'ini es geç (her login fresh olmalı)
  if (url.pathname === '/token' || url.pathname === '/register') return;

  // API rotaları → Network-First (fresh data tercih, offline fallback)
  const isApiRoute = API_ROUTES.some(route => url.pathname.startsWith(route));
  if (isApiRoute) {
    event.respondWith(networkFirst(request, API_CACHE, 5000));
    return;
  }

  // Statik varlıklar → Cache-First (hızlı yükleme)
  event.respondWith(cacheFirst(request, STATIC_CACHE));
});

// ============================================================
// STRATEJİLER
// ============================================================

/**
 * Network-First: Önce ağa git, başarısız olursa cache'ten sun.
 * @param {Request} request
 * @param {string}  cacheName
 * @param {number}  timeoutMs - Ağ timeout (ms)
 */
async function networkFirst(request, cacheName, timeoutMs = 5000) {
  const cache = await caches.open(cacheName);

  try {
    // Timeout + fetch yarışı
    const networkResponse = await Promise.race([
      fetch(request.clone()),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), timeoutMs))
    ]);

    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());  // Başarılı yanıtı cache'e yaz
    }
    return networkResponse;
  } catch {
    // Ağ başarısız → cache'ten sun
    const cached = await cache.match(request);
    if (cached) {
      console.log(`[SW] Offline mod — cache'ten sunuluyor: ${request.url}`);
      return cached;
    }
    // Cache'de de yok → boş 503 döndür
    return new Response(JSON.stringify({ hata: 'Çevrimdışı ve önbellekte de bulunamadı.' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

/**
 * Cache-First: Önce cache'e bak, yoksa ağdan çek ve cache'e yaz.
 * @param {Request} request
 * @param {string}  cacheName
 */
async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  if (cached) return cached;

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}
