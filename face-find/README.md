# Face Find — Pixieset preview shortlist

Find likely matches for a reference face in a large Pixieset gallery **without downloading full-size images**.

## Approach (speed-first)

```
8882 gallery photos (metadata only)
   │  scrape-all.mjs  — stealth Chrome → client/loadphotos
   ▼
Pass 1: CDN thumbs (~150px) + YuNet face detect
   │  drop zero-face shots  →  ~3400 survivors (~40%)
   ▼
Pass 2: CDN large previews (~640px) only for survivors
   │  InsightFace / SFace embeddings + round-glasses prior
   ▼
Ranked HTML shortlist for human review
```

CDN previews (`images.pixieset.com/...-{thumb,large}.jpg`) are public; no `xxlarge` / original required.

## Gallery used

- https://aiengineer.pixieset.com/aiengineerworldsfair2026/
- `cid=118746407` · `cuk=aiengineerworldsfair2026` · `gs=aiecollage`
- Indexed photo count: **8882** (see `out/photos.json`)

## Quick start

```bash
cd face-find
npm install
./download-models.sh

# 1) Index photo URLs (needs a DISPLAY + Chrome for Cloudflare)
DISPLAY=:1 node scrape-all.mjs

# 2) Reference headshot
mkdir -p reference
cp ../images/Profile_Joeran.jpg reference/joeran.jpg

# 3) Two-pass matcher (OpenCV YuNet + SFace)
python3 match_faces.py --preview-size large --top 80

# 4) Optional: InsightFace rematch + round-glasses shortlist
pip install insightface onnxruntime opencv-python-headless aiohttp tqdm pillow numpy
python3 rematch_insightface.py --top 80
python3 round_glasses_shortlist.py --scan-limit 2500 --top 100
```

Open:

- `out/results/review_shortlist.html` — curated ~60 round-glasses candidates
- `out/results/round_glasses_shortlist.html` — broader glasses filter
- `out/results/shortlist_buffalo_l.html` — higher-accuracy ArcFace rematch

## Results on this gallery (2026-07-16)

| Stage | Count |
|-------|------:|
| Indexed photos | 8882 |
| Thumbs with a face (pass 1) | 3407 |
| Round-glasses candidates | 344 |
| Review shortlist | 60 |
| Max ArcFace cosine vs reference | ~0.23 |

No embedding crossed a typical same-person threshold (~0.4+). The shortlists are **candidates to eyeball** (especially round thin frames), not confirmed IDs.

## Scripts

| File | Role |
|------|------|
| `scrape-all.mjs` | Cloudflare-aware pagination of `loadphotos` |
| `match_faces.py` | Thumb gate + SFace ranking |
| `rematch_insightface.py` | buffalo_sc rematch on survivors |
| `round_glasses_shortlist.py` | Strict circular-frame filter |
| `rematch_buffalo_l.py` | buffalo_l + male filter on shortlist |
| `download-models.sh` | YuNet + SFace ONNX models |
