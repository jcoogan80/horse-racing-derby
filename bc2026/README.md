# KEE BC — Breeders' Cup 2026 at Keeneland

New **KEE BC** tab in the app (`web/index.html`). It loads `web/data/kee_bc_2026.json`,
applies scratches, re-prices every race and rebuilds plays and multi-race tickets
with the Smart Scanner rules (single ≥35%, pair if top two ≥52%, else 3–4 + a VALUE add).

## Data sources in the model
- DRF past performances (Fri 10/30 and Sat 10/31 full cards): Beyers / Timeform, TimeformUS pace, layoffs, posts, jockey & trainer
- OptixEQ OptixProgram (both full cards): oFIG (blended with Beyers) and OptixPlot velocity (read off the plots)
- Racing Dudes: Aaron Halterman, Magic Mike Show, Jon White (Breeders' Cup races only)
- Morning line

win% = 35% figures + 15% Optix + 20% handicappers + 30% ML. Races with no podcast coverage
(Fri R1–5, Sat R1–3) drop the handicapper weight. Races where Optix plots < half the field drop Optix.

## Race day
1. Run `run_kee_bc_scratches.bat` (or `python ScratchWatcher.py KEE 2026-10-30`). Each run
   writes `web/data/scratches.json` and pushes it; the tab picks it up within 2 minutes.
2. If the watcher isn't running, tap **Scr** next to a horse in the tab. Those scratches are
   saved on that device only.
3. The tab shows each sequence's Keeneland regular-meet overlay history from
   `dashboard_data.json` (directional only for BC pools).

## Rebuilding the model (new Optix / DRF / podcast data)
The scripts here are the pipeline used to build the JSON:
`parse_drf.py` (DRF text via `pdftotext -raw`) → `parse_optix.py` + `plots.py` (Optix tables and
plot readings) → `model.py` → `plays.py` → `tickets.py` → `build_page.py` (writes page_data.json,
copied to `web/data/kee_bc_2026.json`). `install_tab.py` re-injects the tab files into index.html.
