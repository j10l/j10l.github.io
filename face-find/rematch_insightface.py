#!/usr/bin/env python3
"""
Rematch pass-1 survivors with InsightFace buffalo_sc (better embeddings).
Still preview-only (large CDN), never full-size originals.

Also scores round-ish frames near eye landmarks as a soft prior.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import warnings
from pathlib import Path

import aiohttp
import cv2
import numpy as np
from insightface.app import FaceAnalysis
from tqdm import tqdm

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).resolve().parent


def decode_image(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


async def fetch_bytes(session, url, sem):
    async with sem:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception:
            return None


def cosine(a, b):
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8))


def round_glasses_score(bgr, face) -> float:
    """Soft score for round frames near insightface eye landmarks (kps)."""
    if face.kps is None:
        return 0.0
    kps = face.kps  # 5 points: left_eye, right_eye, nose, left_mouth, right_mouth
    le, re = kps[0], kps[1]
    eye_dist = np.linalg.norm(le - re)
    if eye_dist < 8:
        return 0.0
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    score = 0.0
    for eye in (le, re):
        r = int(max(6, eye_dist * 0.45))
        x0 = int(max(0, eye[0] - r))
        y0 = int(max(0, eye[1] - r))
        x1 = int(min(w, eye[0] + r))
        y1 = int(min(h, eye[1] + r))
        roi = gray[y0:y1, x0:x1]
        if roi.size == 0 or min(roi.shape) < 12:
            continue
        blur = cv2.GaussianBlur(roi, (3, 3), 0)
        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=r,
            param1=120,
            param2=16,
            minRadius=max(3, int(r * 0.25)),
            maxRadius=max(6, int(r * 0.9)),
        )
        if circles is not None:
            score += 0.4
        # dark frame ring vs brighter lens interior
        yy, xx = np.ogrid[: roi.shape[0], : roi.shape[1]]
        cy, cx = roi.shape[0] / 2, roi.shape[1] / 2
        dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        ring = roi[(dist > r * 0.35) & (dist < r * 0.7)]
        core = roi[dist <= r * 0.3]
        if ring.size and core.size and float(ring.mean()) + 8 < float(core.mean()):
            score += 0.15
    return float(min(1.0, score))


def reference_embedding(app: FaceAnalysis, path: Path) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise SystemExit(f"bad reference {path}")
    h, w = img.shape[:2]
    scale = 960 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    faces = app.get(img)
    if not faces:
        raise SystemExit("no face in reference")
    faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
    print(f"ref det={faces[0].det_score:.3f} bbox={faces[0].bbox}")
    return faces[0].normed_embedding


async def rematch(args):
    t0 = time.time()
    survivors = json.loads(Path(args.survivors).read_text())
    # survivors may be list or need photos-shaped; normalize
    if isinstance(survivors, dict) and "photos" in survivors:
        survivors = survivors["photos"]
    print(f"Survivors: {len(survivors)}")

    app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    ref = reference_embedding(app, Path(args.reference))

    if args.limit:
        survivors = survivors[: args.limit]

    sem = asyncio.Semaphore(args.concurrency)
    infer_lock = asyncio.Lock()
    results = []
    lock = asyncio.Lock()

    connector = aiohttp.TCPConnector(limit=args.concurrency, ttl_dns_cache=300)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; face-find/1.1)"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        async def one(photo):
            url = photo["urls"].get(args.preview_size) or photo["urls"]["large"]
            data = await fetch_bytes(session, url, sem)
            if not data:
                return
            img = decode_image(data)
            if img is None:
                return
            async with infer_lock:
                faces = app.get(img)
                if not faces:
                    return
                best = -1.0
                best_face = None
                gboost = 0.0
                for f in faces:
                    sim = cosine(ref, f.normed_embedding)
                    g = round_glasses_score(img, f)
                    gboost = max(gboost, g)
                    if sim > best:
                        best = sim
                        best_face = {
                            "bbox": [float(x) for x in f.bbox.tolist()],
                            "det": float(f.det_score),
                            "glasses": g,
                        }
            if best < 0:
                return
            combined = best + 0.06 * gboost
            rec = {
                "id": photo["id"],
                "name": photo["name"],
                "similarity": round(best, 4),
                "glasses_boost": round(gboost, 4),
                "combined": round(combined, 4),
                "face_count": len(faces),
                "best_face": best_face,
                "urls": photo["urls"],
                "preview": url,
            }
            async with lock:
                results.append(rec)

        tasks = [asyncio.create_task(one(p)) for p in survivors]
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="insightface"):
            await fut

    results.sort(key=lambda r: r["combined"], reverse=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranked_insightface.json").write_text(json.dumps(results, indent=2))

    top = results[: args.top]
    (out / "shortlist_insightface.json").write_text(json.dumps(top, indent=2))

    # Also glasses-prioritized view
    glassesy = [r for r in results if r["glasses_boost"] >= 0.4 and r["similarity"] >= 0.25]
    glassesy.sort(key=lambda r: r["similarity"] + 0.08 * r["glasses_boost"], reverse=True)
    (out / "shortlist_glasses.json").write_text(json.dumps(glassesy[: args.top], indent=2))

    # Save previews
    import urllib.request

    prev_dir = out / "shortlist_insightface_previews"
    prev_dir.mkdir(exist_ok=True)
    for i, c in enumerate(top, 1):
        dest = prev_dir / f"{i:03d}_sim{c['similarity']:.3f}_g{c['glasses_boost']:.2f}_{c['id']}.jpg"
        try:
            urllib.request.urlretrieve(c["preview"], dest)
        except Exception:
            pass

    gdir = out / "shortlist_glasses_previews"
    gdir.mkdir(exist_ok=True)
    for i, c in enumerate(glassesy[: args.top], 1):
        dest = gdir / f"{i:03d}_sim{c['similarity']:.3f}_g{c['glasses_boost']:.2f}_{c['id']}.jpg"
        try:
            urllib.request.urlretrieve(c["preview"], dest)
        except Exception:
            pass

    # HTML
    cards = []
    for i, c in enumerate(top, 1):
        cards.append(
            f"<div class='card'><div class='rank'>#{i} sim={c['similarity']:.3f} "
            f"glasses={c['glasses_boost']:.2f} faces={c['face_count']}</div>"
            f"<a href='{c['urls'].get('xlarge') or c['preview']}' target='_blank'>"
            f"<img loading='lazy' src='{c['preview']}'/></a>"
            f"<div class='meta'>{c['name']}</div></div>"
        )
    html = f"""<!doctype html><html><head><meta charset='utf-8'/>
<title>InsightFace shortlist</title>
<style>
body{{font-family:ui-sans-serif,system-ui;margin:24px;background:#111;color:#eee}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}}
.card{{background:#1a1a1a;border-radius:10px;padding:8px}}
img{{width:100%;height:180px;object-fit:cover;border-radius:6px}}
.rank{{font-size:12px;margin-bottom:6px;opacity:.85}}
.meta{{font-size:11px;opacity:.65;margin-top:6px}}
</style></head><body>
<h1>InsightFace shortlist (top {len(top)} / {len(results)})</h1>
<p>Gallery previews only. Soft round-glasses prior applied.</p>
<div class='grid'>{''.join(cards)}</div>
</body></html>"""
    (out / "shortlist_insightface.html").write_text(html)

    print(f"\nDone in {time.time()-t0:.1f}s — scored {len(results)}")
    sims = np.array([r["similarity"] for r in results]) if results else np.array([0])
    for t in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]:
        print(f"  >= {t}: {(sims >= t).sum()}")
    print("Top 20:")
    for i, c in enumerate(top[:20], 1):
        print(
            f"  {i:2d}. sim={c['similarity']:.3f} g={c['glasses_boost']:.2f} "
            f"faces={c['face_count']} {c['name']}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--survivors", default=str(ROOT / "out/results/survivors_pass1.json"))
    ap.add_argument("--reference", default=str(ROOT / "reference/joeran.jpg"))
    ap.add_argument("--out", default=str(ROOT / "out/results"))
    ap.add_argument("--preview-size", default="large")
    ap.add_argument("--concurrency", type=int, default=48)
    ap.add_argument("--top", type=int, default=80)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    asyncio.run(rematch(args))


if __name__ == "__main__":
    main()
