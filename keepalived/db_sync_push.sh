#!/bin/bash

set -a
source /etc/keepalived/ha.env
set +a


SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_OPTS="-i $SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no"

while true; do
    if sudo -H -u "$SSH_USER" rsync -az --timeout=5 \
        -e "ssh $SSH_OPTS" \
        "$MANAGER_DB_PATH" \
        "${SSH_USER}@${PEER_REAL_IP}:${MANAGER_DB_PATH}" \
        >> "$LOG" 2>&1; then
        :
    else
        echo "$(date) [db_sync_push] WARNING: push to peer failed" >> "$LOG"
    fi
    sleep "$DB_SYNC_INTERVAL"
done
