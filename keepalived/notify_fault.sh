#!/bin/bash
# /etc/keepalived/notify_fault.sh
#
# FAULT means this node's own VRRP health checks failed (not the
# peer's) — e.g. the network interface is down. We don't know if we
# still hold the VIP or not, so the safe move is the same as BACKUP:
# make sure we're NOT running the Manager, to avoid two nodes writing
# to manager_state.db at once (split brain).

source /etc/keepalived/ha.env 2>/dev/null
echo "$(date) [notify_fault] entered FAULT state, ensuring control plane is stopped" >> "${LOG:-/var/log/orchestrator-ha.log}"

/etc/keepalived/notify_backup.sh
