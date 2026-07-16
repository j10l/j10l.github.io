#!/usr/bin/env node
/**
 * Scrape ALL photo metadata from the Pixieset gallery via loadphotos API.
 * Uses stealth Chrome once to clear Cloudflare, then paginates in-page.
 * Does NOT download images — only metadata + preview URL map.
 */
import puppeteer from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

puppeteer.use(StealthPlugin());

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, 'out');
fs.mkdirSync(OUT, { recursive: true });

const GALLERY_URL = process.env.GALLERY_URL || 'https://aiengineer.pixieset.com/aiengineerworldsfair2026/';
const CID = process.env.CID || '118746407';
const CUK = process.env.CUK || 'aiengineerworldsfair2026';
const GS = process.env.GS || 'aiecollage';
const PAGE_SIZE = Number(process.env.PAGE_SIZE || 50);

function absUrl(u) {
  if (!u) return null;
  if (u.startsWith('//')) return 'https:' + u;
  return u;
}

function parsePhotosPayload(text) {
  const outer = JSON.parse(text);
  if (outer.status !== 'success') return { photos: [], raw: outer };
  let content = outer.content;
  if (typeof content === 'string') content = JSON.parse(content);
  if (!Array.isArray(content)) return { photos: [], raw: outer };
  const photos = content.map((p) => ({
    id: p.id,
    idhash: p.idhash,
    name: p.name,
    width: p.width,
    height: p.height,
    gallerySlug: p.gallerySlug,
    urls: {
      thumb: absUrl(p.pathThumb),
      small: absUrl(p.pathSmall),
      medium: absUrl(p.pathMedium),
      large: absUrl(p.pathLarge),
      xlarge: absUrl(p.pathXlarge),
      xxlarge: absUrl(p.pathXxlarge),
    },
  }));
  return { photos, raw: outer };
}

const browser = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome-stable',
  headless: false,
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--window-size=1440,900',
    '--disable-blink-features=AutomationControlled',
  ],
  ignoreDefaultArgs: ['--enable-automation'],
  defaultViewport: null,
});

const page = await browser.newPage();
await page.setUserAgent(
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
);

console.log('Opening gallery to clear Cloudflare...');
await page.goto(GALLERY_URL, { waitUntil: 'networkidle2', timeout: 180000 });

for (let i = 0; i < 30; i++) {
  const title = await page.title();
  if (!/just a moment|security verification/i.test(title)) break;
  await new Promise((r) => setTimeout(r, 1500));
}
console.log('Ready:', await page.title());

const all = [];
const seen = new Set();
let pageNum = 1;
let empty = 0;

while (pageNum <= 500 && empty < 2) {
  const result = await page.evaluate(
    async ({ cuk, cid, gs, pageNum, size }) => {
      const url =
        `/client/loadphotos/?cuk=${encodeURIComponent(cuk)}` +
        `&cid=${cid}&gs=${encodeURIComponent(gs)}&fk=&clientDownloads=false` +
        `&page=${pageNum}&size=${size}`;
      const res = await fetch(url, {
        credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      return { status: res.status, text: await res.text(), url };
    },
    { cuk: CUK, cid: CID, gs: GS, pageNum, size: PAGE_SIZE },
  );

  if (result.status !== 200) {
    console.error('Bad status', result.status, result.url);
    empty += 1;
    pageNum += 1;
    continue;
  }

  const { photos } = parsePhotosPayload(result.text);
  let added = 0;
  for (const p of photos) {
    if (seen.has(p.id)) continue;
    seen.add(p.id);
    all.push(p);
    added += 1;
  }
  console.log(`page ${pageNum}: got ${photos.length}, added ${added}, total ${all.length}`);
  if (photos.length === 0 || added === 0) empty += 1;
  else empty = 0;
  pageNum += 1;
  await new Promise((r) => setTimeout(r, 150));
}

const payload = {
  galleryUrl: GALLERY_URL,
  cid: CID,
  cuk: CUK,
  gs: GS,
  scrapedAt: new Date().toISOString(),
  count: all.length,
  photos: all,
};

const outPath = path.join(OUT, 'photos.json');
fs.writeFileSync(outPath, JSON.stringify(payload, null, 2));
console.log(`Wrote ${all.length} photos -> ${outPath}`);

await browser.close();
