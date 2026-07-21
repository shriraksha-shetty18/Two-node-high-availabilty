#!/bin/bash
# /etc/keepalived/notify_master.sh
#
# keepalived calls this the moment this node takes the VIP and becomes
# MASTER — either because it's the primary node starting up, or because
# it's the slave taking over after the master died.
#
# Identical file on both nodes; ha.env supplies the one thing that
# differs (the peer's real IP).

set -a
source /etc/keepalived/ha.env
set +a

echo "$(date) [notify_master] becoming MASTER, starting control plane" >> "$LOG"

# Best-effort pull of the peer's copy of the DB before we start. If the
# peer just died, this will simply time out and we fall back to
# whatever local copy we have — which, if this node was previously
# BACKUP and running db_sync_pull.sh, should be reasonably fresh.
rsync -az --timeout=5 "${SSH_USER}@${PEER_REAL_IP}:${MANAGER_DB_PATH}" "${MANAGER_DB_PATH}" >> "$LOG" 2>&1 \
    || echo "$(date) [notify_master] could not reach peer for DB pull, using local copy" >> "$LOG"

cd "$MANAGER_DIR" || { echo "$(date) [notify_master] MANAGER_DIR not found: $MANAGER_DIR" >> "$LOG"; exit 1; }

MANAGER_DB_PATH="${MANAGER_DB_PATH}" SCHEDULER_URL="http://localhost:7000" MANAGER_PORT=8000 \
    nohup python3 api.py >> "$LOG" 2>&1 &
echo $! > /var/run/orchestrator-manager.pid

# Now that we're MASTER, start pushing our (now-current) DB to whichever
# node is BACKUP, so it's ready if we're the one that dies next.
nohup bash /etc/keepalived/db_sync_push.sh >> "$LOG" 2>&1 &
echo $! > /var/run/orchestrator-db-sync.pid

echo "$(date) [notify_master] control plane started (manager pid $(cat /var/run/orchestrator-manager.pid))" >> "$LOG"
