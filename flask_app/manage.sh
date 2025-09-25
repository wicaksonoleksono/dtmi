#!/bin/bash

# ----------- CONFIG -------------
source /var/www/optima/env/bin/activate              # Activate virtualenv
APP_MODULE="asgi:application"                    # Your ASGI entrypoint
BIND_ADDR="127.0.0.1:6789"              # Where Hypercorn binds
LOG_FILE="optima.log"                   # Log file path
PID_FILE="hypercorn.pid"                # Where to store Hypercorn PID
WORKERS=1                                # Number of worker processes
# ---------------------------------

start() {
  echo "Starting Hypercorn..."

  # Kill any leftover process bound to same app/bind
  EXISTING=$(pgrep -f "hypercorn $APP_MODULE --bind $BIND_ADDR")
  if [ -n "$EXISTING" ]; then
    echo "Killing old Hypercorn process: $EXISTING"
    kill $EXISTING
    sleep 1
  fi

  nohup hypercorn $APP_MODULE \
    --bind $BIND_ADDR \
    --workers $WORKERS \
    > "$LOG_FILE" 2>&1 &

  echo $! > "$PID_FILE"
  echo "Started Hypercorn (PID $(cat "$PID_FILE")) | Log: $LOG_FILE"
}

stop() {
  echo "Stopping Hypercorn..."
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")"
    rm -f "$PID_FILE"
    echo "Stopped"
  else
    echo "Not running"
    exit 1
  fi
}

restart() {
  stop
  sleep 1
  start
  reload_nginx  # Optional: reload nginx on every restart
}
status() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Running (PID $(cat "$PID_FILE"))"
  else
    echo "Not running"
  fi
}

health() {
  echo "Running health check..."

  if [ ! -f "$LOG_FILE" ]; then
    echo "[SNAFU] Log file not found"
    exit 1
  fi

  if grep -iE "error|traceback" "$LOG_FILE" > /dev/null; then
    echo "[SNAFU] Errors detected in log"
    tail -n 5 "$LOG_FILE"
    exit 1
  else
    echo "[OLLKORECT] No errors found in log"
    tail -n 2 "$LOG_FILE"
  fi

  echo "Checking database..."
  if ps aux | grep -v grep | grep -q "chromadb"; then
    echo "[OLLKORECT] Database process 'DTMI' is running"
  else
    echo "[SNAFU] Database process 'dbtmi' not found"
    exit 1
  fi
}
reload_nginx() {
  echo "Reloading NGINX..."
  if sudo nginx -t; then
    sudo systemctl reload nginx && echo "NGINX reloaded"
  else
    echo "[SNAFU] NGINX config test failed"
    exit 1
  fi
}

case "$1" in
  start|stop|restart|status|health|reload_nginx)
    "$1"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|health|reload_nginx}"
    exit 1
    ;;
esac