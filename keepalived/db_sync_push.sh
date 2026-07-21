#!/bin/bash
# /etc/keepalived/db_sync_push.sh
#
# Started by notify_master.sh. While this node is active (holds the
# VIP, runs the Manager), push manager_state.db to the peer every
# DB_SYNC_INTERVAL seconds so the peer isn't starting from a stale copy
# if it has to take over.

set -a
source /etc/keepalived/ha.env
set +a

while true; do
    rsync -az --timeout=5 "$MANAGER_DB_PATH" "${SSH_USER}@${PEER_REAL_IP}:${MANAGER_DB_PATH}" >> "$LOG" 2>&1
    sleep "$DB_SYNC_INTERVAL"
done
