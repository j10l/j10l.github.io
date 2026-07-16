#!/usr/bin/env node
import puppeteer from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

puppeteer.use(StealthPlugin());

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, 'out');
fs.mkdirSync(OUT, { recursive: true });

const GALLERY_URL = 'https://aiengineer.pixieset.com/aiengineerworldsfair2026/';

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

const hits = [];
page.on('response', async (res) => {
  const url = res.url();
  if (url.includes('loadphotos') || url.includes('/client/') || url.includes('collection')) {
    try {
      const text = await res.text();
      hits.push({ url, status: res.status(), len: text.length, preview: text.slice(0, 3000) });
      console.log('HIT', res.status(), url.slice(0, 160), 'len', text.length);
    } catch {}
  }
});

console.log('goto...');
await page.goto(GALLERY_URL, { waitUntil: 'networkidle2', timeout: 180000 }).catch((e) => console.log('goto err', e.message));

// Give Turnstile time; simulate mild human activity
for (let i = 0; i < 45; i++) {
  const title = await page.title();
  const n = await page.evaluate(() => document.querySelectorAll('img').length);
  console.log(i, title, 'imgs', n);
  if (!/just a moment|security verification/i.test(title) && n > 3) break;
  await page.mouse.move(100 + i * 3, 120 + (i % 5) * 10);
  if (i % 5 === 0) {
    await page.mouse.click(400, 400).catch(() => {});
  }
  await new Promise((r) => setTimeout(r, 2000));
}

// Screenshot for debugging
await page.screenshot({ path: path.join(OUT, 'cf-status.png'), fullPage: false });

const html = await page.content();
fs.writeFileSync(path.join(OUT, 'page.html'), html);
fs.writeFileSync(path.join(OUT, 'hits.json'), JSON.stringify(hits, null, 2));

const info = await page.evaluate(() => ({
  title: document.title,
  url: location.href,
  text: document.body.innerText.slice(0, 2000),
  imgs: [...document.querySelectorAll('img')].slice(0, 30).map((i) => i.src),
}));
console.log(JSON.stringify(info, null, 2));
fs.writeFileSync(path.join(OUT, 'info.json'), JSON.stringify(info, null, 2));

await browser.close();
