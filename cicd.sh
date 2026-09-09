#!/bin/bash
# Wrapper that runs sce-cicd and reacts to the "exit with code 10" self-update
# signal: on code 10 it pulls the latest code, reinstalls deps and relaunches.
# Any other exit code stops the loop.
#
# Usage: ./cicd.sh --config ./path/to/config.yml --restart-on-push <branch>

BRANCH="${RESTART_BRANCH:-main}"   # branch to pull on self-update
PORT="${PORT:-3000}"               # must match server.py --port (default 3000)

while true; do
    echo "Starting SCE CICD Server..."

    # free the port in case a stale server is already running on it
    lsof -ti:"$PORT" | xargs -r kill 2>/dev/null
    sleep 1

    python server.py "$@" &
    PID=$!

    # health-check the existing GET / endpoint to confirm the server came up
    for _ in $(seq 1 15); do
        curl -sf "http://127.0.0.1:$PORT/" >/dev/null && break
        kill -0 "$PID" 2>/dev/null || break   # process already died
        sleep 1
    done

    wait "$PID"
    EXIT_CODE=$?

    if [ "$EXIT_CODE" -eq 10 ]; then
        echo "Self-update triggered. Pulling latest changes..."
        git pull origin "$BRANCH"
        pip install -r requirements.txt
        export SCE_CICD_RESTARTED=1
        echo "Restarting..."
        sleep 2
        continue
    fi

    echo "Server exited with code $EXIT_CODE. Stopping loop."
    break
done
