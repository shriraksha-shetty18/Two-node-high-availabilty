#!/bin/bash
# /etc/keepalived/notify_backup.sh
#
# Called when this node is (or becomes) BACKUP — i.e. it does NOT hold
# the VIP. Only one node should ever run the Manager at a time (it's the
# single writer to manager_state.db), so this stops it here if running,
# and starts a pull loop to stay reasonably in sync with whichever node
# is currently active — so if THIS node has to take over next, it isn't
# starting from a badly stale DB.

set -a
source /etc/keepalived/ha.env
set +a

echo "$(date) [notify_backup] becoming BACKUP, stopping local control plane" >> "$LOG"

for pidfile in /var/run/orchestrator-manager.pid /var/run/orchestrator-db-sync.pid; do
    if [ -f "$pidfile" ]; then
        kill "$(cat "$pidfile")" 2>/dev/null
        rm -f "$pidfile"
    fi
done

echo "$(date) [notify_backup] waiting to receive DB pushes from whichever node is active" >> "$LOG"
