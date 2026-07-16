#!/usr/bin/env python3
"""
Efficient preview-only face shortlist for Pixieset galleries.

Pipeline (speed-first, no full-size downloads):
  1) THUMB GATE  – download tiny thumbs (~150px), YuNet face detect.
                   Drop photos with zero faces. Cheap glasses boost optional.
  2) MEDIUM MATCH – for survivors only, download medium previews (~360px),
                   extract SFace embeddings, rank vs reference face.
  3) Write ranked candidate HTML + JSON for human review.

Usage:
  python3 match_faces.py --photos out/photos.json --reference reference/joeran.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import aiohttp
import cv2
import numpy as np
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
YUNET = MODELS / "face_detection_yunet_2023mar.onnx"
SFACE = MODELS / "face_recognition_sface_2021dec.onnx"


@dataclass
class FaceHit:
    x: int
    y: int
    w: int
    h: int
    score: float


def make_yunet(input_size=(320, 320), score_threshold: float = 0.45):
    return cv2.FaceDetectorYN.create(
        str(YUNET),
        "",
        input_size,
        score_threshold=score_threshold,
        nms_threshold=0.3,
        top_k=50,
    )


def make_sface():
    return cv2.FaceRecognizerSF.create(str(SFACE), "")


@dataclass
class FaceDet:
    hit: FaceHit
    raw: np.ndarray  # full YuNet row including landmarks


def detect_faces(
    detector, bgr: np.ndarray, min_rel_size: float = 0.02
) -> list[FaceDet]:
    h, w = bgr.shape[:2]
    # YuNet works best when very large images are downscaled first
    scale = 1.0
    work = bgr
    max_side = max(h, w)
    if max_side > 1280:
        scale = 1280.0 / max_side
        work = cv2.resize(bgr, (int(w * scale), int(h * scale)))
    wh, ww = work.shape[:2]
    detector.setInputSize((ww, wh))
    _, faces = detector.detect(work)
    hits: list[FaceDet] = []
    if faces is None:
        return hits
    min_side = min(w, h) * min_rel_size
    inv = 1.0 / scale
    for f in faces:
        raw = f.astype(np.float32).copy()
        raw[:14] *= inv  # box + landmarks
        x, y, fw, fh = [int(v) for v in raw[:4]]
        score = float(raw[-1])
        if fw < min_side or fh < min_side:
            continue
        x = max(0, x)
        y = max(0, y)
        fw = min(fw, w - x)
        fh = min(fh, h - y)
        if fw < 8 or fh < 8:
            continue
        raw[0], raw[1], raw[2], raw[3] = x, y, fw, fh
        hits.append(FaceDet(FaceHit(x, y, fw, fh, score), raw))
    return hits


def glasses_boost(gray_face: np.ndarray) -> float:
    """Cheap heuristic: circular/elliptical edge structures in upper face (eye band).
    Returns 0..1 boost; tuned for round metal frames, not a hard filter.
    """
    if gray_face.size == 0:
        return 0.0
    h, w = gray_face.shape[:2]
    if h < 24 or w < 24:
        return 0.0
    # Eye band: ~25%–55% of face height
    y0, y1 = int(h * 0.22), int(h * 0.58)
    band = gray_face[y0:y1, :]
    blur = cv2.GaussianBlur(band, (3, 3), 0)
    edges = cv2.Canny(blur, 60, 140)
    # Hough circles — round frames
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(8, w // 6),
        param1=120,
        param2=18,
        minRadius=max(3, w // 14),
        maxRadius=max(8, w // 3),
    )
    score = 0.0
    edge_density = float(edges.mean()) / 255.0
    if edge_density > 0.04:
        score += min(0.25, edge_density)
    if circles is not None:
        n = circles.shape[1]
        # Two round lenses ideal
        if n >= 2:
            score += 0.55
        elif n == 1:
            score += 0.25
    return float(min(1.0, score))


def align_and_embed(recognizer, bgr: np.ndarray, face: FaceDet) -> Optional[np.ndarray]:
    """Align with YuNet landmarks when available, then SFace embed."""
    try:
        aligned = recognizer.alignCrop(bgr, face.raw)
        feat = recognizer.feature(aligned)
        return feat.flatten().astype(np.float32)
    except Exception:
        f = face.hit
        crop = bgr[f.y : f.y + f.h, f.x : f.x + f.w]
        if crop.size == 0:
            return None
        crop = cv2.resize(crop, (112, 112))
        try:
            feat = recognizer.feature(crop)
            return feat.flatten().astype(np.float32)
        except Exception:
            return None


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
    return float(np.dot(a, b) / denom)


def decode_image(data: bytes) -> Optional[np.ndarray]:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


async def fetch_bytes(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore) -> Optional[bytes]:
    async with sem:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except Exception:
            return None


async def pass1_thumb_gate(
    photos: list[dict],
    concurrency: int,
    min_face_rel: float,
) -> list[dict]:
    """Return photos that contain at least one detectable face in the thumb,
    with face count + glasses boost annotated.
    """
    detector = make_yunet()
    sem = asyncio.Semaphore(concurrency)
    survivors: list[dict] = []
    lock = asyncio.Lock()
    detect_lock = asyncio.Lock()

    connector = aiohttp.TCPConnector(limit=concurrency, ttl_dns_cache=300)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; face-find/1.0)"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        async def one(photo: dict):
            url = photo["urls"]["thumb"]
            data = await fetch_bytes(session, url, sem)
            if not data:
                return
            img = decode_image(data)
            if img is None:
                return
            async with detect_lock:
                faces = detect_faces(detector, img, min_rel_size=min_face_rel)
            if not faces:
                return
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gboost = 0.0
            for fd in faces:
                f = fd.hit
                roi = gray[f.y : f.y + f.h, f.x : f.x + f.w]
                gboost = max(gboost, glasses_boost(roi))
            # Prefer larger relative faces (portraits / close groups)
            max_rel = max(
                (fd.hit.w * fd.hit.h) / float(img.shape[0] * img.shape[1]) for fd in faces
            )
            rec = {
                **photo,
                "thumb_faces": len(faces),
                "thumb_max_face_rel": max_rel,
                "glasses_boost": gboost,
            }
            async with lock:
                survivors.append(rec)

        tasks = [asyncio.create_task(one(p)) for p in photos]
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="pass1 thumbs"):
            await f

    return survivors


async def pass2_medium_match(
    photos: list[dict],
    ref_embedding: np.ndarray,
    concurrency: int,
    size_key: str = "medium",
) -> list[dict]:
    detector = make_yunet()
    recognizer = make_sface()
    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []
    lock = asyncio.Lock()
    infer_lock = asyncio.Lock()

    connector = aiohttp.TCPConnector(limit=concurrency, ttl_dns_cache=300)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; face-find/1.0)"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        async def one(photo: dict):
            url = photo["urls"].get(size_key) or photo["urls"]["medium"]
            data = await fetch_bytes(session, url, sem)
            if not data:
                return
            img = decode_image(data)
            if img is None:
                return
            async with infer_lock:
                faces = detect_faces(detector, img, min_rel_size=0.015)
                if not faces:
                    return
                best_sim = -1.0
                best_face = None
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                gboost = photo.get("glasses_boost", 0.0)
                for fd in faces:
                    emb = align_and_embed(recognizer, img, fd)
                    if emb is None:
                        continue
                    sim = cosine(ref_embedding, emb)
                    if sim > best_sim:
                        best_sim = sim
                        best_face = asdict(fd.hit)
                    f = fd.hit
                    roi = gray[f.y : f.y + f.h, f.x : f.x + f.w]
                    gboost = max(gboost, glasses_boost(roi))

            if best_sim < 0:
                return

            # Combined ranking score: similarity primary, glasses as soft boost
            combined = best_sim + 0.04 * gboost
            rec = {
                "id": photo["id"],
                "name": photo["name"],
                "similarity": round(best_sim, 4),
                "glasses_boost": round(gboost, 4),
                "combined": round(combined, 4),
                "face_count": len(faces),
                "best_face": best_face,
                "thumb_faces": photo.get("thumb_faces"),
                "thumb_max_face_rel": photo.get("thumb_max_face_rel"),
                "urls": photo["urls"],
                "preview": photo["urls"].get(size_key) or photo["urls"]["medium"],
            }
            async with lock:
                results.append(rec)

        tasks = [asyncio.create_task(one(p)) for p in photos]
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"pass2 {size_key}"):
            await f

    results.sort(key=lambda r: r["combined"], reverse=True)
    return results


def reference_embedding(path: Path) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise SystemExit(f"Cannot read reference image: {path}")
    detector = make_yunet(score_threshold=0.3)
    recognizer = make_sface()
    faces = detect_faces(detector, img, min_rel_size=0.02)
    if not faces:
        raise SystemExit("No face found in reference image")
    # largest face
    faces.sort(key=lambda fd: fd.hit.w * fd.hit.h, reverse=True)
    emb = align_and_embed(recognizer, img, faces[0])
    if emb is None:
        raise SystemExit("Failed to embed reference face")
    print(
        f"Reference face: {faces[0].hit.w}x{faces[0].hit.h} score={faces[0].hit.score:.3f}"
    )
    return emb


def write_html(candidates: list[dict], out_html: Path, top_n: int, reference: Path):
    rows = []
    for i, c in enumerate(candidates[:top_n], 1):
        rows.append(
            f"""
            <div class="card">
              <div class="rank">#{i} sim={c['similarity']:.3f} glasses={c['glasses_boost']:.2f}</div>
              <a href="{c['urls'].get('xlarge') or c['urls'].get('large') or c['preview']}" target="_blank">
                <img loading="lazy" src="{c['preview']}" alt="{c['name']}"/>
              </a>
              <div class="meta">{c['name']} · faces={c['face_count']}<br/>
              <a href="{c['urls']['large']}" target="_blank">large</a> ·
              <a href="{c['urls'].get('xlarge') or '#'}" target="_blank">xlarge</a>
              </div>
            </div>"""
        )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"/>
<title>Face shortlist</title>
<style>
body{{font-family:ui-sans-serif,system-ui;margin:24px;background:#111;color:#eee}}
h1{{font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}}
.card{{background:#1b1b1b;border-radius:10px;overflow:hidden;padding:8px}}
.card img{{width:100%;height:180px;object-fit:cover;border-radius:6px;background:#000}}
.rank{{font-size:12px;opacity:.85;margin-bottom:6px}}
.meta{{font-size:11px;opacity:.7;margin-top:6px;word-break:break-all}}
.ref{{max-width:180px;border-radius:8px;margin:12px 0}}
</style></head><body>
<h1>Face shortlist ({min(top_n, len(candidates))} of {len(candidates)} scored)</h1>
<p>Reference:</p>
<img class="ref" src="file://{reference}"/>
<div class="grid">{''.join(rows)}</div>
</body></html>"""
    out_html.write_text(html)


def save_candidate_previews(candidates: list[dict], out_dir: Path, top_n: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    import urllib.request

    for i, c in enumerate(candidates[:top_n], 1):
        url = c["preview"]
        dest = out_dir / f"{i:03d}_sim{c['similarity']:.3f}_{c['id']}.jpg"
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            print("download fail", url, e)


async def amain(args):
    t0 = time.time()
    photos_doc = json.loads(Path(args.photos).read_text())
    photos = photos_doc["photos"]
    print(f"Loaded {len(photos)} photos from index")

    if not YUNET.exists() or not SFACE.exists():
        raise SystemExit("Missing models in models/ — download YuNet + SFace first")

    ref_emb = reference_embedding(Path(args.reference))
    print("Reference embedding ready")

    # Optional: restrict for testing
    if args.limit:
        photos = photos[: args.limit]
        print(f"Limited to first {len(photos)} photos")

    survivors = await pass1_thumb_gate(photos, args.concurrency, args.min_face_rel)
    print(
        f"Pass1: {len(survivors)}/{len(photos)} thumbs have faces "
        f"({100.0 * len(survivors) / max(1, len(photos)):.1f}%)"
    )

    # Soft pre-rank: prefer glasses + larger faces to optionally truncate pass2
    survivors.sort(
        key=lambda p: (p.get("glasses_boost", 0) * 0.5 + p.get("thumb_max_face_rel", 0)),
        reverse=True,
    )
    if args.pass2_limit and len(survivors) > args.pass2_limit:
        # Always keep strong glasses candidates, then fill by face size
        glassesy = [p for p in survivors if p.get("glasses_boost", 0) >= 0.35]
        rest = [p for p in survivors if p.get("glasses_boost", 0) < 0.35]
        keep = glassesy[: args.pass2_limit]
        if len(keep) < args.pass2_limit:
            keep.extend(rest[: args.pass2_limit - len(keep)])
        print(f"Pass2 truncated to {len(keep)} (glasses-priority) from {len(survivors)}")
        survivors = keep

    ranked = await pass2_medium_match(
        survivors, ref_emb, args.concurrency, size_key=args.preview_size
    )
    print(f"Pass2: scored {len(ranked)} images")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "survivors_pass1.json").write_text(json.dumps(survivors, indent=2))
    (out_dir / "ranked.json").write_text(json.dumps(ranked, indent=2))

    top = ranked[: args.top]
    (out_dir / "shortlist.json").write_text(json.dumps(top, indent=2))
    write_html(ranked, out_dir / "shortlist.html", args.top, Path(args.reference).resolve())
    save_candidate_previews(ranked, out_dir / "shortlist_previews", args.top)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print(f"Shortlist: {out_dir / 'shortlist.html'}")
    print(f"Top {min(args.top, len(ranked))} similarities:")
    for i, c in enumerate(top, 1):
        print(
            f"  {i:2d}. sim={c['similarity']:.3f} glasses={c['glasses_boost']:.2f} "
            f"faces={c['face_count']} {c['name']} {c['preview']}"
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photos", default=str(ROOT / "out" / "photos.json"))
    ap.add_argument("--reference", default=str(ROOT / "reference" / "joeran.jpg"))
    ap.add_argument("--out", default=str(ROOT / "out" / "results"))
    ap.add_argument("--concurrency", type=int, default=48)
    ap.add_argument("--min-face-rel", type=float, default=0.02, help="Min face area vs thumb area")
    ap.add_argument("--preview-size", default="medium", choices=["small", "medium", "large"])
    ap.add_argument("--pass2-limit", type=int, default=0, help="Max images for embedding pass (0=all survivors)")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--limit", type=int, default=0, help="Debug: only first N photos")
    args = ap.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
