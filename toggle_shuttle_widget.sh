#!/bin/bash
# Toggle the shuttle menu bar widget on/off.
#
#   bash toggle_shuttle_widget.sh              # start if stopped, stop if running
#   bash toggle_shuttle_widget.sh --make-app   # create a double-clickable
#                                              # "Shuttle Widget.app" in ~/Applications
set -e
cd "$(dirname "$0")"
PROJECT="$(pwd)"
PY="$PROJECT/.venv/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"
LOG=/tmp/shuttle_widget.log

check_deps() {
  "$PY" -c "import rumps, google.transit" 2>/dev/null || {
    echo "Missing dependencies for $PY — run: uv sync" >&2
    exit 1
  }
}

if [ "$1" = "--make-app" ]; then
  check_deps
  APP="$HOME/Applications/Shuttle Widget.app"
  mkdir -p "$APP/Contents/MacOS"
  cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Shuttle Widget</string>
  <key>CFBundleIdentifier</key><string>local.lbnl-shuttle-widget</string>
  <key>CFBundleExecutable</key><string>ShuttleWidget</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST
  cat > "$APP/Contents/MacOS/ShuttleWidget" <<LAUNCH
#!/bin/bash
cd "$PROJECT"
exec "$PY" menubar_shuttle.py >> /tmp/shuttle_widget.log 2>&1
LAUNCH
  chmod +x "$APP/Contents/MacOS/ShuttleWidget"
  echo "Created: $APP  (double-click to start; Quit from the menu to stop)"
  exit 0
fi

if pgrep -f "[m]enubar_shuttle" > /dev/null; then
  pkill -f "[m]enubar_shuttle"
  echo "Shuttle widget stopped."
else
  check_deps
  nohup "$PY" "$PROJECT/menubar_shuttle.py" > "$LOG" 2>&1 &
  sleep 2
  if pgrep -f "[m]enubar_shuttle" > /dev/null; then
    echo "Shuttle widget started — look for 🚌 in the menu bar. (log: $LOG)"
  else
    echo "Widget failed to start — last log lines:" >&2
    tail -5 "$LOG" >&2
    exit 1
  fi
fi
