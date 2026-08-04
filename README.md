# LBNL Shuttle Menu Bar Widget

A tiny macOS menu bar widget that shows a live countdown to the next LBNL
shuttle at your stop: `🚌 12m` while you have time, `🎒 5m` once you're
within `pack_minutes` of having to leave, then `🏃 2m` at your leave time
(the departure minus `walk_minutes`). Both of those are yours to set — see
[Configure your stop](#configure-your-stop). The dropdown lists the next
departures with live delay info from the shuttle's realtime feed.

Data comes from LBNL's public TripShot GTFS + GTFS-realtime feeds — no
API key needed.

## Install

Requires macOS and Python ≥ 3.10.

```bash
git clone https://github.com/jaeminy00/lbnl-shuttle-widget.git
cd lbnl-shuttle-widget
uv sync                      # or: python3 -m venv .venv && .venv/bin/pip install .
```

### Dependencies

Two packages, both from PyPI (no conda-forge needed):
[rumps](https://pypi.org/project/rumps/) (menu bar UI) and
[gtfs-realtime-bindings](https://pypi.org/project/gtfs-realtime-bindings/)
(realtime feed parsing). Any environment manager works — with conda:

```bash
conda create -n shuttle python=3.12
conda activate shuttle
pip install .
```

If you're not using the project's `.venv`, activate your environment
before running the widget or the toggle script (it uses `.venv` when
present, otherwise whatever `python3` is on your PATH), and replace
`.venv/bin/python3` with `python3` in the commands below.

## Configure your stop

The default is **Blue Route Downhill at B48 Firehouse**. To use a
different route/stop, copy the example config and edit it:

```bash
cp config.example.json config.json
```

- `route` — route short or long name (e.g. `"Blue Route Uphill"`,
  `"Orange"`; a unique fragment also works)
- `stop` — stop name, stop id, or a unique fragment of the name

### Timing

Two settings decide which of the three menu bar states you see. The values
shipped in `config.example.json` are just the estimates that work for us —
they're placeholders, so set them to your own:

- `walk_minutes` — how long it takes *you* to get from your desk to the
  stop. Your **leave time** is `departure − walk_minutes`.
- `pack_minutes` — how much notice you want before that leave time, to
  shut the laptop and grab your things. Set it to `0` to skip the 🎒 state
  entirely.

Which state shows when:

| when | looks like | color key |
| --- | --- | --- |
| more than `pack_minutes` before your leave time | 🚌 12m | `title_color` |
| within `pack_minutes` of it — pack up | 🎒 5m | `pack_title_color` |
| at your leave time or later — go now | 🏃 2m | `urgent_title_color` |

The countdown always shows minutes until the shuttle *departs*, not minutes
until you have to leave, so 🏃 appears with roughly `walk_minutes` still on
the clock.

### Colors

- `title_color` / `pack_title_color` / `urgent_title_color` — menu bar text
  color per state. `null` keeps the system default; otherwise use a name
  (`"yellow"`, `"red"`, `"orange"`, `"green"`, `"blue"`, `"purple"`,
  `"gray"`, `"white"`, …) or a hex value (`"#ff8800"`). Named colors adapt
  to light/dark menu bars; hex values and `"white"` don't, so pick
  something that reads on both — plain `"white"` is invisible on a
  light-mode menu bar. The emoji keeps its own colors either way.

Find your stop's exact name (and which routes serve it):

```bash
.venv/bin/python3 menubar_shuttle.py --stops "b48"
.venv/bin/python3 menubar_shuttle.py --stops "oxford"
```

Check your config resolves before launching the widget:

```bash
.venv/bin/python3 menubar_shuttle.py --test
```

## Run

```bash
bash toggle_shuttle_widget.sh              # start; run again to stop
bash toggle_shuttle_widget.sh --make-app   # make a double-clickable
                                           # "Shuttle Widget.app" in /Applications
```

The app is a toggle too: double-click to start, double-click again to stop.

The widget refreshes every 30 s. Quit it from its own dropdown menu, the
toggle script, or by quitting "Shuttle Widget" in Activity Monitor.
If it doesn't appear in the menu bar, check `/tmp/shuttle_widget.log`.

## How it works

One Python file. The GTFS schedule zip is cached for 24 h in
`~/.cache/shuttle-menubar`; the realtime feed is polled every 30 s and
matched to scheduled trips by `trip_id` (predictions are absolute times;
delay is computed against the schedule). Cancelled trips and skipped
stops are dropped. The menu bar UI is [rumps](https://github.com/jaredks/rumps).

## Offline testing

```bash
SHUTTLE_OFFLINE="path/to/gtfs.zip:path/to/rt.pb" python3 menubar_shuttle.py --test
```
