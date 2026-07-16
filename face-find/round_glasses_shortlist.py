#!/usr/bin/env python3
"""
Build a human-review shortlist focused on distinctive ROUND glasses.

Uses existing InsightFace ranked results when available, and/or rescans
pass-1 survivors on large previews with a stricter round-frame check.

Output: a smaller gallery of candidates to eyeball — not claimed IDs.
"""

from __future__ import annotations

import argparse
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


def decode(data: bytes):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def cosine(a, b):
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8))


def strict_round_glasses(bgr, face) -> tuple[float, dict]:
    """Stricter round-frame score using eye landmarks + circular Hough + aspect."""
    info = {"circles": 0, "aspect": None, "ring": 0.0}
    if face.kps is None:
        return 0.0, info
    le, re = face.kps[0], face.kps[1]
    eye_dist = float(np.linalg.norm(le - re))
    if eye_dist < 10:
        return 0.0, info

    # Face aspect: round glasses wearers often have visible frame width ~ face
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    fw, fh = max(1, x2 - x1), max(1, y2 - y1)
    info["aspect"] = round(fw / fh, 3)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    score = 0.0
    found = 0
    ring_hits = 0
    for eye in (le, re):
        r = int(max(7, eye_dist * 0.42))
        x0, y0 = int(max(0, eye[0] - r)), int(max(0, eye[1] - r))
        x1e, y1e = int(min(W, eye[0] + r)), int(min(H, eye[1] + r))
        roi = gray[y0:y1e, x0:x1e]
        if min(roi.shape[:2]) < 14:
            continue
        blur = cv2.GaussianBlur(roi, (5, 5), 0)
        circles = cv2.HoughCircles(
            blur,
            cv2.HOUGH_GRADIENT,
            dp=1.15,
            minDist=max(6, r // 2),
            param1=100,
            param2=18,
            minRadius=max(4, int(r * 0.28)),
            maxRadius=max(7, int(r * 0.85)),
        )
        if circles is not None:
            found += 1
            score += 0.35
        yy, xx = np.ogrid[: roi.shape[0], : roi.shape[1]]
        cy, cx = roi.shape[0] / 2.0, roi.shape[1] / 2.0
        dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        ring = roi[(dist > r * 0.4) & (dist < r * 0.75)]
        core = roi[dist <= r * 0.28]
        if ring.size > 20 and core.size > 10:
            delta = float(core.mean()) - float(ring.mean())
            if delta > 10:
                ring_hits += 1
                score += 0.15
    info["circles"] = found
    info["ring"] = ring_hits
    # Prefer two circular lenses
    if found >= 2:
        score += 0.25
    if ring_hits >= 2:
        score += 0.15
    return float(min(1.0, score)), info


async def fetch(session, url, sem):
    async with sem:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as r:
                if r.status != 200:
                    return None
                return await r.read()
        except Exception:
            return None


async def main_async(args):
    survivors = json.loads(Path(args.survivors).read_text())
    # Prefer faces that are reasonably large on thumb (portraits / close groups)
    survivors = sorted(
        survivors,
        key=lambda p: (
            p.get("glasses_boost", 0) * 0.4 + float(p.get("thumb_max_face_rel") or 0)
        ),
        reverse=True,
    )
    if args.limit:
        survivors = survivors[: args.limit]
    else:
        # Cap scan for speed: prioritize likely portrait/glasses thumbs
        survivors = survivors[: args.scan_limit]

    app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))

    ref_img = cv2.imread(args.reference)
    h, w = ref_img.shape[:2]
    scale = 960 / max(h, w)
    if scale < 1:
        ref_img = cv2.resize(ref_img, (int(w * scale), int(h * scale)))
    ref_faces = app.get(ref_img)
    ref_faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
    ref = ref_faces[0].normed_embedding
    ref_g, ref_info = strict_round_glasses(ref_img, ref_faces[0])
    print(f"Reference glasses score={ref_g:.2f} info={ref_info}")

    sem = asyncio.Semaphore(args.concurrency)
    lock = asyncio.Lock()
    infer_lock = asyncio.Lock()
    hits = []

    connector = aiohttp.TCPConnector(limit=args.concurrency)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; face-find/1.2)"}
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        async def one(photo):
            url = photo["urls"].get(args.preview_size) or photo["urls"]["large"]
            data = await fetch(session, url, sem)
            if not data:
                return
            img = decode(data)
            if img is None:
                return
            async with infer_lock:
                faces = app.get(img)
                if not faces:
                    return
                best = None
                for f in faces:
                    g, ginfo = strict_round_glasses(img, f)
                    if g < args.min_glasses:
                        continue
                    sim = cosine(ref, f.normed_embedding)
                    cand = {
                        "similarity": round(sim, 4),
                        "glasses": round(g, 4),
                        "glasses_info": ginfo,
                        "det": float(f.det_score),
                        "bbox": [float(x) for x in f.bbox.tolist()],
                        "face_area_rel": float(
                            (f.bbox[2] - f.bbox[0])
                            * (f.bbox[3] - f.bbox[1])
                            / (img.shape[0] * img.shape[1])
                        ),
                    }
                    if best is None or cand["similarity"] > best["similarity"]:
                        best = cand
            if best is None:
                return
            rec = {
                "id": photo["id"],
                "name": photo["name"],
                **best,
                "combined": round(best["similarity"] + 0.12 * best["glasses"], 4),
                "urls": photo["urls"],
                "preview": url,
            }
            async with lock:
                hits.append(rec)

        tasks = [asyncio.create_task(one(p)) for p in survivors]
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="round-glasses"):
            await fut

    hits.sort(key=lambda r: r["combined"], reverse=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "round_glasses_shortlist.json").write_text(json.dumps(hits, indent=2))

    top = hits[: args.top]
    prev = out / "round_glasses_previews"
    prev.mkdir(exist_ok=True)
    for i, c in enumerate(top, 1):
        dest = prev / f"{i:03d}_sim{c['similarity']:.3f}_g{c['glasses']:.2f}_{c['id']}.jpg"
        try:
            urllib.request.urlretrieve(c["preview"], dest)
        except Exception:
            pass

    cards = []
    for i, c in enumerate(top, 1):
        cards.append(
            f"<div class='card'><div class='rank'>#{i} sim={c['similarity']:.3f} "
            f"roundGlasses={c['glasses']:.2f}</div>"
            f"<a href='{c['urls'].get('xlarge') or c['preview']}' target='_blank'>"
            f"<img loading='lazy' src='{c['preview']}'/></a>"
            f"<div class='meta'>{c['name']} · faceRel={c['face_area_rel']:.3f}</div></div>"
        )
    html = f"""<!doctype html><html><head><meta charset='utf-8'/>
<title>Round-glasses shortlist</title>
<style>
body{{font-family:ui-sans-serif,system-ui;margin:24px;background:#0f1115;color:#eee}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}}
.card{{background:#1a1d24;border-radius:10px;padding:8px}}
img{{width:100%;height:190px;object-fit:cover;border-radius:6px}}
.rank{{font-size:12px;margin-bottom:6px;opacity:.9}}
.meta{{font-size:11px;opacity:.65;margin-top:6px}}
.note{{max-width:720px;opacity:.8;line-height:1.45}}
</style></head><body>
<h1>Round-glasses candidates ({len(top)} shown / {len(hits)} matched)</h1>
<p class='note'>Filtered for circular frames near the eyes, then ranked by face similarity
to the reference. These are <b>candidates to eyeball</b> — not confirmed matches.
Previews only (CDN <code>-large</code>), no full-size downloads.</p>
<div class='grid'>{''.join(cards)}</div>
</body></html>"""
    (out / "round_glasses_shortlist.html").write_text(html)
    print(f"Wrote {len(hits)} round-glasses hits; top {len(top)} saved")
    for i, c in enumerate(top[:25], 1):
        print(
            f"  {i:2d}. sim={c['similarity']:.3f} g={c['glasses']:.2f} "
            f"rel={c['face_area_rel']:.3f} {c['name']}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--survivors", default=str(ROOT / "out/results/survivors_pass1.json"))
    ap.add_argument("--reference", default=str(ROOT / "reference/joeran.jpg"))
    ap.add_argument("--out", default=str(ROOT / "out/results"))
    ap.add_argument("--preview-size", default="large")
    ap.add_argument("--concurrency", type=int, default=48)
    ap.add_argument("--min-glasses", type=float, default=0.55)
    ap.add_argument("--scan-limit", type=int, default=2000)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--top", type=int, default=100)
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
