#!/bin/bash

set -a
source /etc/keepalived/ha.env
set +a
export HOME="$(getent passwd "$SSH_USER" | cut -d: -f6)"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_OPTS="-i $SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no"

echo "$(date) [notify_master] becoming MASTER" >> "$LOG"

# Pull the peer database using the SSH identity of shriraksha.
if sudo -H -u "$SSH_USER" rsync -az --timeout=5 \
    -e "ssh $SSH_OPTS" \
    "${SSH_USER}@${PEER_REAL_IP}:${MANAGER_DB_PATH}" \
    "$MANAGER_DB_PATH" \
    >> "$LOG" 2>&1; then
    echo "$(date) [notify_master] Database synchronized from peer" >> "$LOG"
else
    echo "$(date) [notify_master] Peer unavailable; retaining local database" >> "$LOG"
fi

# Stop an old Manager if one exists.
if [ -f /var/run/orchestrator-manager.pid ]; then
    OLD_PID=$(cat /var/run/orchestrator-manager.pid)
    kill "$OLD_PID" 2>/dev/null || true
    rm -f /var/run/orchestrator-manager.pid
fi

# Stop an old DB sync process if one exists.
if [ -f /var/run/orchestrator-db-sync.pid ]; then
    OLD_PID=$(cat /var/run/orchestrator-db-sync.pid)
    kill "$OLD_PID" 2>/dev/null || true
    rm -f /var/run/orchestrator-db-sync.pid
fi

(
    cd "$MANAGER_DIR" || exit 1

    export PYTHONPATH="/home/shriraksha/.local/lib/python3.12/site-packages"
    export MANAGER_DB_PATH
    export SCHEDULER_URL="http://localhost:7000"
    export MANAGER_PORT=8000

    exec python3 api.py
) >> "$LOG" 2>&1 &


echo $! > /var/run/orchestrator-manager.pid

nohup /etc/keepalived/db_sync_push.sh >> "$LOG" 2>&1 &
echo $! > /var/run/orchestrator-db-sync.pid

echo "$(date) [notify_master] Manager and DB sync started" >> "$LOG"
