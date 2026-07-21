# HA failover with keepalived

Replaces the earlier rsync + inotifywait heartbeat setup entirely — this
is a bigger change: keepalived now handles master↔slave liveness
detection AND full control-plane failover (not just workload
rescheduling).

## What moves and what doesn't

| Component | Where it runs |
|---|---|
| **Worker** | Always on, both nodes — untouched by keepalived |
| **Scheduler** | Always on, both nodes — stateless, safe to run on both simultaneously |
| **Manager** | **Floats** — runs on exactly one node: whichever holds the VIP |

The Manager is the only thing that moves, because it's the only thing
with state (`manager_state.db`). Running it on both nodes at once would
mean two processes writing the same SQLite file — that's the split-brain
scenario this whole setup exists to avoid.

Clients — your frontend, or anyone hitting the API — always talk to the
**VIP**, never to either node's real IP for the Manager. The Scheduler
is also reachable at `VIP:7000` for the same reason (both nodes run it,
so whichever one currently owns the VIP answers).

## How failover actually happens

1. Both nodes run `keepalived`, exchanging VRRP advertisements every 1s.
2. Master (priority 150) normally holds the VIP and is in `MASTER` state.
3. If master stops sending advertisements (crashed, network down, etc),
   the slave promotes itself to `MASTER`, claims the VIP, and keepalived
   runs `notify_master.sh` on it.
4. `notify_master.sh` pulls the latest `manager_state.db` from the peer
   (best-effort — the peer is probably unreachable, which is fine, it
   falls back to whatever was last pushed) and starts the Manager
   locally.
5. From then on, the now-active node pushes its DB to the peer every
   `DB_SYNC_INTERVAL` seconds via `db_sync_push.sh`, so the peer has a
   reasonably fresh copy if roles flip again.

## Setup

**1. Install keepalived on both nodes:**
```bash
sudo apt install keepalived
```

**2. SSH key auth in BOTH directions** (master→slave and slave→master),
since either node might need to push/pull the DB from the other:
```bash
# on each node
ssh-keygen -t ed25519 -f ~/.ssh/orchestrator_key -N ""
ssh-copy-id -i ~/.ssh/orchestrator_key.pub orchestrator@<other-node-ip>
```

**3. Copy configs into place:**
- On the master: `keepalived-master.conf` → `/etc/keepalived/keepalived.conf`
- On the slave: `keepalived-slave.conf` → `/etc/keepalived/keepalived.conf`
- On **both**: `notify_master.sh`, `notify_backup.sh`, `notify_fault.sh`,
  `db_sync_push.sh` → `/etc/keepalived/`, then `chmod +x` all of them
- On **both**: `ha.env` → `/etc/keepalived/ha.env` — **edit `PEER_REAL_IP`
  on each node to point at the other node's real (non-VIP) address**

**4. Edit the interface name and VIP** in both `.conf` files to match
your actual network (`ip a` to find your interface name).

**5. Deploy the Manager code itself** to `/opt/orchestrator/manager` on
**both** nodes (the notify scripts `cd` into it) — same files from the
`manager/` folder, `pip install -r requirements.txt` on both.

**6. Start Worker + Scheduler as always-on systemd services** on both
nodes — see `systemd-units-reference.txt`. Start keepalived last:
```bash
sudo systemctl enable --now keepalived
```

## Failing back to master

Because the master's config has `nopreempt`, a recovered master does
**not** automatically reclaim the VIP — it stays BACKUP even though its
priority is higher. This is intentional: automatic failback could yank
the VIP mid-request, and risks the recovered node briefly running the
Manager against a DB that's older than what the slave has been writing.

To fail back manually once you've confirmed the recovered master is
healthy and its DB has caught up (its `notify_backup` state means it's
been receiving pushes from the slave the whole time it was down, so it
should already be close):
```bash
# on the master
sudo systemctl restart keepalived
```
This re-triggers VRRP election; since `nopreempt` only blocks *automatic*
preemption, a manual restart still lets priority decide, and master
reclaims the VIP.

## Known limitations (worth stating plainly in your report)

- **Not instant.** VRRP failover typically takes ~3× `advert_int`
  (so ~3 seconds here) to detect a dead master, plus however long the
  DB pull + Manager startup takes. This isn't a zero-downtime system.
- **Last-write-wins, not conflict-free.** If both nodes briefly think
  they're master (a real network partition, not just a crash), you can
  get two SQLite files diverging before one gets overwritten by the next
  push. For a 2-node college project this is an acceptable simplification
  to name explicitly, not something to silently paper over — real HA
  systems use consensus protocols (Raft/etcd) instead of last-write-wins
  precisely to avoid this.
- **Workers themselves have no failover** — they were never meant to;
  each Worker only ever manages containers on its own machine. If a
  physical node dies, whatever containers were running via *its own*
  Worker are gone too, VIP or not. VIP failover here is about keeping
  the *control plane* (Manager) reachable, not about magically resurrecting
  containers on a dead machine.
