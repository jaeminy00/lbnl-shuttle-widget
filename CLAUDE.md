# lbnl-shuttle-widget — project memory

## What this is
macOS menu bar widget (Python + rumps) showing a live countdown to the next
LBNL shuttle at a configured stop. Menu bar shows "🚌 7m", switching to
"🏃 3m" when departure minus walk time is < 2 min. Dropdown lists the next
departures with live/sched tags and delays. Owner: Jae (jaeminyoo@lbl.gov).
Goal: publish on GitHub so lab colleagues can clone and run with their own
stop config.

## Files
- `menubar_shuttle.py` — everything: GTFS parsing, realtime merge, rumps UI.
  CLI modes: `--test` (print instead of menu bar), `--stops "text"` (search
  stops in the feed and show which routes serve them).
- `toggle_shuttle_widget.sh` — start/stop toggle; `--make-app` builds a
  double-clickable "Shuttle Widget.app" in ~/Applications (LSUIElement, no
  Dock icon).
- `config.example.json` — copy to `config.json` (gitignored) to override
  route/stop/walk_minutes/etc. Defaults in code: Blue Route Downhill @
  B48 Firehouse, walk 3 min.
- `pyproject.toml` — deps: gtfs-realtime-bindings, rumps (darwin-marked).
  Python >= 3.10. Env managed with uv (`uv sync`).

## Current state / immediate next step
- Startup-crash fix (`quit_button=None` + own Quit MenuItem) verified on
  real macOS 2026-08-04: widget ran through multiple 30s ticks/menu
  rebuilds with no errors. Quit-button *click* still needs a human eyeball.
- `toggle_shuttle_widget.sh` improvements applied and tested: dep check
  (`import rumps, google.transit` → "run uv sync" hint), logs to
  /tmp/shuttle_widget.log (also from the .app launcher), post-launch
  pgrep verify with log tail on failure. Toggle stop/start and
  `--make-app` all exercised successfully.
- data pipeline is verified (offline test with real feed files produced
  correct live departures).

## Known TODO
- Git + publish — **Jae does this themselves** (don't run git init/commit):
  `git init`, commit (uv.lock included; .gitignore already covers
  config.json/.venv/.claude settings), then
  `gh repo create lbnl-shuttle-widget --public --source . --push`.
- README.md is written for colleagues; keep it in sync with changes.

## Feed facts (hard-won, do not rediscover)
- LBNL TripShot GTFS static:
  `https://lbnl.tripshot.com/v1/gtfs.zip?regionId=CA558DDC-D7F2-4B48-9CAC-DEEA1134F820`
  GTFS-RT: `https://lbnl.tripshot.com/v1/gtfs/realtime/CA558DDC-D7F2-4B48-9CAC-DEEA1134F820`
  No API key. Cached 24h in ~/.cache/shuttle-menubar.
- TripShot GTFS-RT quirks: TripUpdates carry NO route_id (join via trip_id
  through static trips.txt); the `delay` field is always 0 (compute delay
  as predicted_time − scheduled_time); predictions are absolute epoch
  times — match to the day's scheduled run within ±6h (trip_ids repeat daily).
- Stop "B48 Firehouse" = stop_id 48; route "Blue Route Downhill";
  ~79 departures/day, 06:56–20:26, weekdays.
- GTFS times can exceed 24:00; service-day epoch is computed DST-safely as
  (local noon − 12h) + seconds. Timezone America/Los_Angeles.
- Offline testing: `SHUTTLE_OFFLINE="path/gtfs.zip:path/rt.pb" python3 menubar_shuttle.py --test`

## Sibling project (separate folder, don't entangle)
`~/dev/projects/shuttle-dash` — the living-room web departure board
(multi-source: LBNL TripShot, AC Transit GTFS w/ token, BART ETD API w/ token
rate-limited to ~1 req/45s, Bear Transit pending a 511.org token). The widget
was extracted from it; leftover copies live in `shuttle-dash/_to_delete/`
(user should delete). Don't add mac-only deps to shuttle-dash — it deploys
to a Raspberry Pi via `uv sync`.
