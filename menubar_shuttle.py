#!/usr/bin/env python3
"""
LBNL shuttle menu bar widget (macOS).

Shows a live countdown to the next LBNL shuttle at your stop in the macOS
menu bar ("🚌 7m", switching to "🏃 3m" when it's time to leave). The
dropdown lists upcoming departures; Quit turns the widget off.

Quick start:
    uv sync                                   # or: pip install .
    python3 menubar_shuttle.py --test         # check your config prints times
    bash toggle_shuttle_widget.sh             # start/stop the widget
    bash toggle_shuttle_widget.sh --make-app  # double-clickable app in ~/Applications

Configure your stop by copying config.example.json to config.json and
editing it. Find your stop's exact name with:
    python3 menubar_shuttle.py --stops "b48"

Data: LBNL's public TripShot GTFS + GTFS-realtime feeds.
"""

import csv
import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------ config

DEFAULTS = {
    "gtfs_url": ("https://lbnl.tripshot.com/v1/gtfs.zip"
                 "?regionId=CA558DDC-D7F2-4B48-9CAC-DEEA1134F820"),
    "rt_url": ("https://lbnl.tripshot.com/v1/gtfs/realtime/"
               "CA558DDC-D7F2-4B48-9CAC-DEEA1134F820"),
    "route": "Blue Route Downhill",   # route short or long name
    "stop": "B48 Firehouse",          # stop name, stop_id, or unique fragment
    "walk_minutes": 3,                # your walk to the stop
    "show_departures": 4,             # rows in the dropdown
    "poll_seconds": 30,
    "timezone": "America/Los_Angeles",
    "cache_dir": "~/.cache/shuttle-menubar",
}


def load_cfg():
    cfg = dict(DEFAULTS)
    path = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            cfg.update(json.load(f))
    cfg["cache_dir"] = os.path.expanduser(cfg["cache_dir"])
    return cfg


CFG = load_cfg()
TZ = ZoneInfo(CFG["timezone"])

# Offline testing: SHUTTLE_OFFLINE="path/to/gtfs.zip:path/to/rt.pb"
OFFLINE = os.environ.get("SHUTTLE_OFFLINE", "")


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.4.0",
                                               "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

# ------------------------------------------------ static schedule


class Static:
    """Minimal GTFS parse for one route+stop, with fuzzy resolution."""

    def __init__(self, zip_bytes):
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))

        def rows(name):
            if name not in z.namelist():
                return
            with z.open(name) as f:
                yield from csv.DictReader(io.TextIOWrapper(f, "utf-8-sig"))

        # route: exact short/long name, then substring
        q = CFG["route"].strip().lower()
        routes = {r["route_id"]: (r.get("route_short_name", ""),
                                  r.get("route_long_name", ""))
                  for r in rows("routes.txt")}
        rids = {rid for rid, (s, l) in routes.items()
                if s.strip().lower() == q or l.strip().lower() == q}
        if not rids and len(q) >= 2:
            rids = {rid for rid, (s, l) in routes.items()
                    if q in s.lower() or q in l.lower()}
        if not rids:
            avail = sorted({l or s for s, l in routes.values()})
            raise RuntimeError(f"route '{CFG['route']}' not found. "
                               f"Available: {', '.join(avail)}")

        # stop candidates: id, exact name, then fragment
        sq = CFG["stop"].strip().lower()
        stops = {r["stop_id"]: r["stop_name"] for r in rows("stops.txt")}
        cand = [sid for sid in stops if sid == CFG["stop"]] \
            or [sid for sid, nm in stops.items() if nm.strip().lower() == sq] \
            or [sid for sid, nm in stops.items() if sq in nm.lower()]
        if not cand:
            raise RuntimeError(f"no stop matches '{CFG['stop']}' "
                               f"(try --stops to search)")
        cand = set(cand)

        self.trip_service = {r["trip_id"]: r["service_id"]
                             for r in rows("trips.txt") if r["route_id"] in rids}
        # collect stop_times at candidate stops; disambiguate by service
        by_stop = {}
        for r in rows("stop_times.txt"):
            if r["trip_id"] in self.trip_service and r["stop_id"] in cand:
                if r.get("pickup_type", "0") == "1":
                    continue
                h, m, s = (int(x) for x in
                           (r["departure_time"] or r["arrival_time"]).split(":"))
                by_stop.setdefault(r["stop_id"], {})[r["trip_id"]] = \
                    h * 3600 + m * 60 + s
        if not by_stop:
            raise RuntimeError(f"route '{CFG['route']}' does not serve any "
                               f"stop matching '{CFG['stop']}'")
        if len(by_stop) > 1:
            names = "; ".join(f"{stops[s]} (id {s})" for s in by_stop)
            raise RuntimeError(f"'{CFG['stop']}' is ambiguous — served stops: "
                               f"{names}. Put the exact name or id in config.json.")
        self.stop_id, self.stop_dep = next(iter(by_stop.items()))
        self.stop_name = stops[self.stop_id]

        self.calendar = list(rows("calendar.txt"))
        self.calendar_dates = {(r["service_id"], r["date"]): r["exception_type"]
                               for r in rows("calendar_dates.txt")}

    def services_on(self, d: date):
        ymd = d.strftime("%Y%m%d")
        days = ["monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday"]
        active = {r["service_id"] for r in self.calendar
                  if r[days[d.weekday()]] == "1"
                  and r["start_date"] <= ymd <= r["end_date"]}
        for (sid, day), ex in self.calendar_dates.items():
            if day == ymd:
                (active.add if ex == "1" else active.discard)(sid)
        return active

    def upcoming(self, rt, now, horizon_h=26):
        out = []
        today = datetime.fromtimestamp(now, TZ).date()
        for d in (today - timedelta(days=1), today, today + timedelta(days=1)):
            active = self.services_on(d)
            noon = datetime(d.year, d.month, d.day, 12, tzinfo=TZ)
            base = (noon - timedelta(hours=12)).timestamp()
            for trip_id, secs in self.stop_dep.items():
                if self.trip_service[trip_id] not in active:
                    continue
                t = base + secs
                if not (now - 30 * 60 < t < now + horizon_h * 3600):
                    continue
                if trip_id in rt.get("cancelled", set()):
                    continue
                item = {"time": t, "realtime": False, "delay": 0}
                stu = rt.get("updates", {}).get(trip_id, {}).get(self.stop_id)
                if stu and stu.get("skipped"):
                    continue
                if stu and stu.get("time") and abs(stu["time"] - t) < 6 * 3600:
                    item.update(time=stu["time"], realtime=True,
                                delay=round(stu["time"] - t))
                out.append(item)
        out.sort(key=lambda x: x["time"])
        return [x for x in out if x["time"] >= now - 30]

# ------------------------------------------------ data loading


def gtfs_bytes(force=False):
    if OFFLINE:
        return open(OFFLINE.split(":")[0].strip(), "rb").read()
    os.makedirs(CFG["cache_dir"], exist_ok=True)
    cache = os.path.join(CFG["cache_dir"], "gtfs.zip")
    if (not force and os.path.exists(cache)
            and time.time() - os.path.getmtime(cache) < 24 * 3600):
        return open(cache, "rb").read()
    data = http_get(CFG["gtfs_url"], timeout=60)
    with open(cache, "wb") as f:
        f.write(data)
    return data


def fetch_rt():
    if OFFLINE:
        data = open(OFFLINE.split(":")[1].strip(), "rb").read()
    else:
        data = http_get(CFG["rt_url"], timeout=20)
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    updates, cancelled = {}, set()
    for e in feed.entity:
        if not e.HasField("trip_update"):
            continue
        tu = e.trip_update
        if tu.trip.schedule_relationship == tu.trip.CANCELED:
            cancelled.add(tu.trip.trip_id)
            continue
        stops = {}
        for stu in tu.stop_time_update:
            t = (stu.departure.time if stu.HasField("departure")
                 and stu.departure.time else
                 stu.arrival.time if stu.HasField("arrival") else None)
            stops[stu.stop_id] = {"time": t,
                                  "skipped": stu.schedule_relationship == stu.SKIPPED}
        updates[tu.trip.trip_id] = stops
    return {"updates": updates, "cancelled": cancelled}

# ------------------------------------------------ formatting


def fmt(deps, now):
    if not deps:
        return "🚌 —", ["No shuttles in the next 24 h"]
    mins0 = (deps[0]["time"] - now) / 60
    icon = "🏃" if mins0 - CFG["walk_minutes"] < 2 else "🚌"
    whole = int(mins0)
    title = (f"{icon} {whole}m" if whole < 100
             else f"{icon} {whole // 60}h{whole % 60:02d}")
    lines = []
    for d in deps:
        t = datetime.fromtimestamp(d["time"], TZ).strftime("%-I:%M %p")
        mins = int((d["time"] - now) / 60)
        tag = "live" if d["realtime"] else "sched"
        delay = (f"  +{round(d['delay'] / 60)}m" if d["delay"] >= 60
                 else f"  {round(d['delay'] / 60)}m" if d["delay"] <= -60 else "")
        lines.append(f"{t}   in {mins} min   ({tag}{delay})")
    return title, lines

# ------------------------------------------------ CLI helpers


def run_stops(text):
    z = zipfile.ZipFile(io.BytesIO(gtfs_bytes()))

    def rows(name):
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, "utf-8-sig"))

    ql = text.strip().lower()
    matches = {r["stop_id"]: r["stop_name"] for r in rows("stops.txt")
               if ql in r["stop_name"].lower() or r["stop_id"] == text}
    if not matches:
        print("no stops match")
        return
    route_names = {r["route_id"]: (r.get("route_long_name")
                                   or r.get("route_short_name", ""))
                   for r in rows("routes.txt")}
    trip_route = {r["trip_id"]: r["route_id"] for r in rows("trips.txt")}
    serving = {}
    for r in rows("stop_times.txt"):
        if r["stop_id"] in matches:
            serving.setdefault(r["stop_id"], set()).add(
                route_names.get(trip_route.get(r["trip_id"], ""), "?"))
    for sid, nm in sorted(matches.items(), key=lambda kv: kv[1]):
        print(f"  {nm}  [id {sid}]  routes: "
              f"{', '.join(sorted(serving.get(sid, {'(no service)'})))}")


def run_test():
    st = Static(gtfs_bytes())
    print(f"resolved: {CFG['route']} @ {st.stop_name} (stop id {st.stop_id})")
    rt = {}
    try:
        rt = fetch_rt()
    except Exception as ex:
        print("rt fetch failed:", ex)
    now = time.time()
    title, lines = fmt(st.upcoming(rt, now)[:CFG["show_departures"]], now)
    print("title:", title)
    for ln in lines:
        print("  ", ln)

# ------------------------------------------------ menu bar app


def run_app():
    import rumps

    class ShuttleApp(rumps.App):
        def __init__(self):
            # quit_button=None: we manage the menu (incl. Quit) ourselves —
            # letting rumps auto-add its quit item collides with our rebuilds
            super().__init__("🚌 …", quit_button=None)
            self.static = None
            self.rt = {}
            self.timer = rumps.Timer(self.tick, CFG["poll_seconds"])
            self.timer.start()
            self.tick(None)

        def tick(self, _):
            now = time.time()
            try:
                if self.static is None:
                    self.static = Static(gtfs_bytes())
                elif not OFFLINE:
                    cache = os.path.join(CFG["cache_dir"], "gtfs.zip")
                    if time.time() - os.path.getmtime(cache) > 24 * 3600:
                        self.static = Static(gtfs_bytes(force=True))
            except Exception as ex:
                self.title = "🚌 ?"
                self.rebuild_menu([f"schedule error: {ex}"])
                return
            try:
                self.rt = fetch_rt()
                rt_note = None
            except Exception:
                rt_note = "live data unavailable — showing schedule"
            deps = self.static.upcoming(self.rt, now)[:CFG["show_departures"]]
            self.title, lines = fmt(deps, now)
            if rt_note:
                lines.append(rt_note)
            self.rebuild_menu(lines)

        def rebuild_menu(self, lines):
            self.menu.clear()
            head = (f"{CFG['route']} · "
                    f"{self.static.stop_name if self.static else CFG['stop']}")
            items = [rumps.MenuItem(head)]
            items += [rumps.MenuItem(ln) for ln in lines]
            items += [None,
                      rumps.MenuItem("Refresh now", callback=self.tick),
                      None,
                      rumps.MenuItem("Quit", callback=rumps.quit_application)]
            self.menu.update(items)

    ShuttleApp().run()


if __name__ == "__main__":
    if "--stops" in sys.argv:
        i = sys.argv.index("--stops")
        run_stops(sys.argv[i + 1] if len(sys.argv) > i + 1 else "")
    elif "--test" in sys.argv:
        run_test()
    else:
        run_app()
