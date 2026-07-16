# Face Find — Pixieset preview shortlist

Find likely matches for a reference face in a large Pixieset gallery **without downloading full-size images**.

## Approach

1. **Scrape metadata only** (`scrape-all.mjs`) — stealth Chrome clears Cloudflare, then paginates `client/loadphotos` for thumb/small/medium/large URLs.
2. **Pass 1 — thumb gate** (`match_faces.py`) — download ~150px thumbs, YuNet face detect, drop zero-face shots. Soft “round glasses” heuristic boosts candidates.
3. **Pass 2 — medium/large match** — download preview stills only for survivors, SFace embeddings vs reference, rank shortlist.

CDN previews (`images.pixieset.com/...-thumb|medium|large.jpg`) are public; no full-res `xxlarge` required.

## Quick start

```bash
cd face-find
npm install
# 1) Index gallery photo URLs (needs DISPLAY / Chrome)
DISPLAY=:1 node scrape-all.mjs

# 2) Put a reference headshot at reference/joeran.jpg (or pass --reference)

# 3) Match (models auto-expected under models/)
python3 match_faces.py --preview-size large --top 60
```

Open `out/results/shortlist.html` to review candidates.

## Notes

- Gallery used: https://aiengineer.pixieset.com/aiengineerworldsfair2026/ (`cid=118746407`, `gs=aiecollage`)
- Scores are cosine similarities from OpenCV SFace — use as a ranking aid, not ground truth.
- Round metal glasses are treated as a soft prior because they are distinctive in the reference.
