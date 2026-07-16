#!/usr/bin/env node
/**
 * Scrape Pixieset gallery photo metadata (preview URLs only).
 * Uses Chrome to pass Cloudflare, then paginates client/loadphotos.
 */
import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const GALLERY_URL = process.env.GALLERY_URL || 'https://aiengineer.pixieset.com/aiengineerworldsfair2026/';
const OUT_DIR = path.join(__dirname, 'out');
const META_PATH = path.join(OUT_DIR, 'photos.json');

fs.mkdirSync(OUT_DIR, { recursive: true });

function pickPreviewUrl(photo) {
  // Prefer smallest useful preview for speed: thumb > small > medium
  const candidates = [
    photo.thumb,
    photo.thumbnail,
    photo.small,
    photo.medium,
    photo.url_thumb,
    photo.url_small,
    photo.url_medium,
    photo.src,
    photo.url,
  ].filter(Boolean);

  // Also scan nested objects / common Pixieset shapes
  for (const key of Object.keys(photo)) {
    const v = photo[key];
    if (typeof v === 'string' && /\.(jpe?g|webp|png)/i.test(v) && /thumb|small|medium|preview/i.test(key + v)) {
      candidates.push(v);
    }
  }
  if (photo.images && typeof photo.images === 'object') {
    for (const size of ['thumb', 'thumbnail', 'small', 'medium', 'large']) {
      if (photo.images[size]) candidates.push(photo.images[size]);
    }
  }
  return candidates[0] || null;
}

function normalizePhoto(raw, page) {
  const preview = pickPreviewUrl(raw);
  return {
    id: raw.id ?? raw.pid ?? raw.photo_id ?? null,
    name: raw.name ?? raw.filename ?? raw.title ?? null,
    page,
    preview,
    // keep size map if present for later selective upgrade
    sizes: {
      thumb: raw.thumb || raw.thumbnail || raw.url_thumb || raw?.images?.thumb || null,
      small: raw.small || raw.url_small || raw?.images?.small || null,
      medium: raw.medium || raw.url_medium || raw?.images?.medium || null,
      large: raw.large || raw.url_large || raw?.images?.large || null,
      xlarge: raw.xlarge || raw.url_xlarge || raw?.images?.xlarge || null,
    },
    rawKeys: Object.keys(raw),
  };
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome-stable',
    headless: false, // needed for Cloudflare challenge
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1400,900',
    ],
    defaultViewport: { width: 1400, height: 900 },
  });

  const page = await browser.newPage();
  const loadphotosHits = [];

  page.on('response', async (res) => {
    try {
      const url = res.url();
      if (!url.includes('loadphotos')) return;
      const ct = res.headers()['content-type'] || '';
      if (!ct.includes('json') && !ct.includes('text') && !ct.includes('javascript')) {
        // still try
      }
      const text = await res.text();
      loadphotosHits.push({ url, status: res.status(), body: text.slice(0, 500000) });
      console.log(`[net] loadphotos ${res.status()} ${url.slice(0, 120)}`);
    } catch (e) {
      // response body may already be consumed
    }
  });

  console.log('Navigating to gallery...');
  await page.goto(GALLERY_URL, { waitUntil: 'domcontentloaded', timeout: 120000 });

  // Wait for Cloudflare / gallery content
  for (let i = 0; i < 60; i++) {
    const title = await page.title();
    const hasPhotos = await page.evaluate(() => {
      return document.querySelectorAll('img').length > 5 ||
        document.body.innerText.includes('Load more') ||
        !!document.querySelector('[class*="photo"], [class*="gallery"], [data-photo]');
    });
    console.log(`wait ${i}: title="${title}" imgs/content=${hasPhotos}`);
    if (!title.includes('Just a moment') && hasPhotos) break;
    await new Promise((r) => setTimeout(r, 2000));
  }

  // Extract collection params from page / network
  const pageInfo = await page.evaluate(() => {
    const html = document.documentElement.innerHTML;
    const cid = (html.match(/["']cid["']\s*:\s*["']?(\d+)/) || html.match(/cid=(\d+)/) || [])[1] || null;
    const cuk = (html.match(/["']cuk["']\s*:\s*["']([^"']+)/) || html.match(/cuk=([a-z0-9_-]+)/i) || [])[1] || null;
    const gs = (html.match(/["']gs["']\s*:\s*["']([^"']+)/) || html.match(/gs=([a-z0-9_-]+)/i) || [])[1] || null;
    const scripts = [...document.scripts].map((s) => s.src).filter(Boolean);
    const imgSamples = [...document.querySelectorAll('img')].slice(0, 20).map((img) => ({
      src: img.src,
      dataSrc: img.getAttribute('data-src'),
      className: img.className,
      width: img.naturalWidth,
      height: img.naturalHeight,
    }));
    return {
      title: document.title,
      url: location.href,
      cid,
      cuk,
      gs,
      scripts: scripts.slice(0, 30),
      imgSamples,
      bodySnippet: document.body.innerText.slice(0, 1500),
    };
  });

  console.log('Page info:', JSON.stringify(pageInfo, null, 2));
  fs.writeFileSync(path.join(OUT_DIR, 'page-info.json'), JSON.stringify(pageInfo, null, 2));

  // Click "Load more" repeatedly to trigger pagination, while also trying API
  for (let i = 0; i < 40; i++) {
    const clicked = await page.evaluate(() => {
      const buttons = [...document.querySelectorAll('button, a, div, span')];
      const btn = buttons.find((el) => /load more/i.test(el.textContent || '') && el.offsetParent !== null);
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    });
    if (!clicked) {
      console.log(`Load more not found at iteration ${i}`);
      break;
    }
    console.log(`Clicked Load more #${i + 1}`);
    await new Promise((r) => setTimeout(r, 1500));
  }

  // Wait a bit for last responses
  await new Promise((r) => setTimeout(r, 3000));

  // Try to call loadphotos directly from the page context with cookies
  const apiProbe = await page.evaluate(async (info) => {
    const results = [];
    const cuk = info.cuk || 'aiengineerworldsfair2026';
    const candidates = [];
    if (info.cid) {
      for (const gs of [info.gs, 'highlights', 'all', 'proofs', ''].filter((x) => x !== null && x !== undefined)) {
        candidates.push(`/client/loadphotos/?cuk=${cuk}&cid=${info.cid}&gs=${gs}&fk=&page=1`);
      }
    }
    // Also try scraping from window globals
    const globals = {};
    for (const k of Object.keys(window)) {
      try {
        if (/pixie|gallery|collection|photo/i.test(k)) {
          const v = window[k];
          globals[k] = typeof v === 'object' ? JSON.parse(JSON.stringify(v, (_, val) => {
            if (typeof val === 'function') return undefined;
            return val;
          })) : v;
        }
      } catch {}
    }

    for (const path of candidates) {
      try {
        const res = await fetch(path, { credentials: 'include', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const text = await res.text();
        results.push({ path, status: res.status, body: text.slice(0, 200000) });
      } catch (e) {
        results.push({ path, error: String(e) });
      }
    }
    return { results, globals: Object.keys(globals), globalsSample: globals };
  }, pageInfo);

  fs.writeFileSync(path.join(OUT_DIR, 'api-probe.json'), JSON.stringify(apiProbe, null, 2));
  fs.writeFileSync(path.join(OUT_DIR, 'loadphotos-hits.json'), JSON.stringify(
    loadphotosHits.map((h) => ({ url: h.url, status: h.status, bodyPreview: h.body.slice(0, 2000), bodyLen: h.body.length })),
    null,
    2,
  ));

  // Parse all photos from intercepted + probed responses
  const photos = [];
  const seen = new Set();

  function ingestBody(body, pageNum) {
    let data;
    try {
      data = JSON.parse(body);
    } catch {
      return;
    }
    const lists = [];
    if (Array.isArray(data)) lists.push(data);
    if (Array.isArray(data.photos)) lists.push(data.photos);
    if (Array.isArray(data.data)) lists.push(data.data);
    if (Array.isArray(data.items)) lists.push(data.items);
    if (data.content && Array.isArray(data.content.photos)) lists.push(data.content.photos);
    if (typeof data.html === 'string') {
      // extract image urls from html fragments
      const re = /https?:\/\/[^"'\\\s]+?\.(?:jpe?g|webp|png)/gi;
      const urls = data.html.match(re) || [];
      for (const url of urls) {
        if (seen.has(url)) continue;
        seen.add(url);
        photos.push({ id: null, name: null, page: pageNum, preview: url, sizes: {}, rawKeys: ['html'] });
      }
    }
    for (const list of lists) {
      for (const raw of list) {
        const n = normalizePhoto(raw, pageNum);
        const key = n.preview || JSON.stringify(n.id);
        if (!key || seen.has(key)) continue;
        seen.add(key);
        photos.push(n);
      }
    }
  }

  for (const hit of loadphotosHits) ingestBody(hit.body, 0);
  for (const r of apiProbe.results || []) if (r.body) ingestBody(r.body, 0);

  // Also collect all currently loaded img URLs from DOM
  const domImgs = await page.evaluate(() => {
    return [...document.querySelectorAll('img')].map((img) => ({
      src: img.currentSrc || img.src,
      dataSrc: img.getAttribute('data-src'),
      dataOriginal: img.getAttribute('data-original'),
      alt: img.alt,
      w: img.naturalWidth,
      h: img.naturalHeight,
    }));
  });
  fs.writeFileSync(path.join(OUT_DIR, 'dom-imgs.json'), JSON.stringify(domImgs, null, 2));

  for (const img of domImgs) {
    const url = img.dataSrc || img.dataOriginal || img.src;
    if (!url || !/^https?:/i.test(url)) continue;
    if (/logo|icon|avatar|emoji|sprite|pixel|blank|placeholder/i.test(url)) continue;
    if (seen.has(url)) continue;
    seen.add(url);
    photos.push({
      id: null,
      name: img.alt || null,
      page: 0,
      preview: url,
      sizes: {},
      rawKeys: ['dom'],
      width: img.w,
      height: img.h,
    });
  }

  // If we found cid, paginate API until empty
  let cid = pageInfo.cid;
  if (!cid && loadphotosHits[0]) {
    cid = (loadphotosHits[0].url.match(/cid=(\d+)/) || [])[1];
  }
  const cuk = pageInfo.cuk || 'aiengineerworldsfair2026';
  let gs = pageInfo.gs || 'highlights';
  if (loadphotosHits[0]) {
    gs = (loadphotosHits[0].url.match(/gs=([^&]*)/) || [])[1] || gs;
  }

  if (cid) {
    console.log(`Paginating API cid=${cid} cuk=${cuk} gs=${gs}`);
    let pageNum = 1;
    let emptyStreak = 0;
    while (pageNum <= 200 && emptyStreak < 2) {
      const result = await page.evaluate(async ({ cuk, cid, gs, pageNum }) => {
        const path = `/client/loadphotos/?cuk=${encodeURIComponent(cuk)}&cid=${cid}&gs=${encodeURIComponent(gs)}&fk=&page=${pageNum}`;
        const res = await fetch(path, { credentials: 'include', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const text = await res.text();
        return { status: res.status, text, path };
      }, { cuk, cid, gs, pageNum });

      const before = photos.length;
      ingestBody(result.text, pageNum);
      const added = photos.length - before;
      console.log(`page ${pageNum}: status=${result.status} added=${added} total=${photos.length}`);
      fs.writeFileSync(path.join(OUT_DIR, `loadphotos-page-${pageNum}.json`), result.text.slice(0, 500000));

      if (added === 0) emptyStreak += 1;
      else emptyStreak = 0;
      pageNum += 1;
      await new Promise((r) => setTimeout(r, 250));
    }
  } else {
    console.log('No cid found — relying on DOM / intercepted responses only');
  }

  const payload = {
    galleryUrl: GALLERY_URL,
    scrapedAt: new Date().toISOString(),
    count: photos.length,
    cid,
    cuk,
    gs,
    photos,
  };
  fs.writeFileSync(META_PATH, JSON.stringify(payload, null, 2));
  console.log(`Wrote ${photos.length} photos to ${META_PATH}`);

  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
