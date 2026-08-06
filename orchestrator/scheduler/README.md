# Scheduler

Decides which node — master or slave — a workload runs on, then forwards
it to that node's Worker API. The Scheduler never touches Docker directly;
placement decision and execution are kept separate, same as
kube-scheduler vs kubelet in real Kubernetes.

## Policy

Prefer the master. Only place on the slave if the master is:
- **dead** — its Worker `/health` endpoint doesn't respond in time, or
- **busy** — its running container count is at/over `capacity`

If both nodes are dead or busy, scheduling fails with a clear error rather
than hanging or guessing.

If placement on the chosen node fails mid-flight (e.g. it died between the
health check and the actual request), the scheduler retries once on the
other node automatically.

## Files

- `scheduler.py` — core `Scheduler` class: `choose_node()`, `schedule()`,
  plus `stop`/`remove`/`status` pass-throughs to whichever node a
  container is on.
- `api.py` — Flask REST API so the Manager (and later the frontend) can
  call `/schedule` without knowing or caring which node it lands on.

## Run it

Run this on the master node (or wherever the Manager will live) — it just
needs network access to both Worker APIs:

```bash
pip install -r requirements.txt

MASTER_URL=http://192.168.1.10:6000 \
SLAVE_URL=http://192.168.1.20:6001 \
python api.py
```

## Using it

```bash
# Schedule a workload — scheduler decides master vs slave internally
curl -X POST http://localhost:7000/schedule \
  -H 'Content-Type: application/json' \
  -d '{"image":"nginx:latest","name":"web-1","ports":{"80/tcp":8080},"restart_policy":"always"}'
# -> {"node_id": "master-1", "container_id": "..."}

# Check both nodes' health/load — good for a frontend status panel
curl http://localhost:7000/nodes/status

# Stop/remove/inspect — needs node_id since the caller (Manager) tracks that
curl -X POST http://localhost:7000/containers/master-1/<container_id>/stop
curl -X DELETE http://localhost:7000/containers/master-1/<container_id>?force=true
curl http://localhost:7000/containers/master-1/<container_id>
```

## Where this plugs in

- **Manager → Scheduler**: the Manager calls `/schedule` when the user
  clicks "deploy" on the frontend, and records which node the container
  landed on (the scheduler's response tells it).
- **Manager → failover**: when the health monitor detects the slave is
  dead, the Manager should call `/schedule` again for each of the slave's
  workloads — since master is preferred anyway, they'll land on the master
  automatically as long as it has capacity.
- **Note on capacity**: `capacity` here is just "max running container
  count," not real CPU/memory bin-packing. Fine for a college project;
  worth mentioning as a known simplification if asked in a viva.
