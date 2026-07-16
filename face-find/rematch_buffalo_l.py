#!/usr/bin/env python3
"""High-accuracy rematch with buffalo_l + male filter on round-glasses candidates."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

import aiohttp
import cv2
import numpy as np
from insightface.app import FaceAnalysis
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent


def cosine(a, b):
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8))


def decode(data: bytes):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


async def fetch(session, url, sem):
    async with sem:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as r:
                return await r.read() if r.status == 200 else None
        except Exception:
            return None


async def main():
    candidates = json.loads((ROOT / "out/results/round_glasses_shortlist.json").read_text())
    # also include top insightface ranked for coverage
    extra = json.loads((ROOT / "out/results/ranked_insightface.json").read_text())[:400]
    by_id = {c["id"]: c for c in candidates}
    for e in extra:
        by_id.setdefault(e["id"], e)
    photos = list(by_id.values())
    print(f"Rematching {len(photos)} candidates with buffalo_l")

    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))

    ref = cv2.imread(str(ROOT / "reference/joeran.jpg"))
    h, w = ref.shape[:2]
    s = 960 / max(h, w)
    if s < 1:
        ref = cv2.resize(ref, (int(w * s), int(h * s)))
    rf = app.get(ref)
    rf.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
    ref_emb = rf[0].normed_embedding
    print(f"ref gender={rf[0].sex} age={rf[0].age} det={rf[0].det_score:.3f}")

    sem = asyncio.Semaphore(32)
    lock = asyncio.Lock()
    infer_lock = asyncio.Lock()
    results = []

    connector = aiohttp.TCPConnector(limit=32)
    headers = {"User-Agent": "Mozilla/5.0 face-find/buffalo_l"}
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        async def one(photo):
            url = photo["urls"].get("large") or photo["preview"]
            data = await fetch(session, url, sem)
            if not data:
                return
            img = decode(data)
            if img is None:
                return
            async with infer_lock:
                faces = app.get(img)
                best = None
                for f in faces:
                    # 1 = male in insightface
                    sex = getattr(f, "sex", None)
                    if sex is not None and sex != "M":
                        continue
                    sim = cosine(ref_emb, f.normed_embedding)
                    rec = {
                        "similarity": round(sim, 4),
                        "sex": sex,
                        "age": int(getattr(f, "age", -1) or -1),
                        "det": float(f.det_score),
                        "bbox": [float(x) for x in f.bbox.tolist()],
                    }
                    if best is None or rec["similarity"] > best["similarity"]:
                        best = rec
            if best is None:
                return
            out = {
                "id": photo["id"],
                "name": photo["name"],
                **best,
                "urls": photo["urls"],
                "preview": url,
                "prior_glasses": photo.get("glasses") or photo.get("glasses_boost"),
            }
            async with lock:
                results.append(out)

        tasks = [asyncio.create_task(one(p)) for p in photos]
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="buffalo_l"):
            await fut

    results.sort(key=lambda r: r["similarity"], reverse=True)
    outdir = ROOT / "out/results"
    (outdir / "ranked_buffalo_l.json").write_text(json.dumps(results, indent=2))

    top = results[:80]
    prev = outdir / "buffalo_l_previews"
    prev.mkdir(exist_ok=True)
    for i, c in enumerate(top, 1):
        dest = prev / f"{i:03d}_sim{c['similarity']:.3f}_{c['id']}.jpg"
        try:
            urllib.request.urlretrieve(c["preview"], dest)
        except Exception:
            pass

    cards = []
    for i, c in enumerate(top, 1):
        cards.append(
            f"<div class='card'><div class='rank'>#{i} sim={c['similarity']:.3f} "
            f"age≈{c['age']} glasses={c.get('prior_glasses')}</div>"
            f"<a href='{c['urls'].get('xlarge') or c['preview']}' target='_blank'>"
            f"<img loading='lazy' src='{c['preview']}'/></a>"
            f"<div class='meta'>{c['name']}</div></div>"
        )
    html = f"""<!doctype html><html><head><meta charset=utf-8>
<title>buffalo_l shortlist</title>
<style>
body{{margin:24px;background:#0e1014;color:#eee;font-family:ui-sans-serif,system-ui}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}}
.card{{background:#191c22;border-radius:10px;padding:8px}}
img{{width:100%;height:200px;object-fit:cover;border-radius:6px}}
.rank{{font-size:12px;margin-bottom:6px}}
.meta{{font-size:11px;opacity:.65;margin-top:6px}}
</style></head><body>
<h1>buffalo_l male shortlist (top {len(top)} / {len(results)})</h1>
<p>Higher-accuracy ArcFace rematch on round-glasses + prior candidates. Male filter applied.</p>
<div class='grid'>{''.join(cards)}</div>
</body></html>"""
    (outdir / "shortlist_buffalo_l.html").write_text(html)

    sims = np.array([r["similarity"] for r in results]) if results else np.array([0.0])
    print(f"scored {len(results)} max={sims.max():.3f}")
    for t in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55]:
        print(f"  >= {t}: {(sims >= t).sum()}")
    print("Top 25:")
    for i, c in enumerate(top[:25], 1):
        print(
            f"  {i:2d}. sim={c['similarity']:.3f} age={c['age']} "
            f"g={c.get('prior_glasses')} {c['name']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
