# Manager

The brain of the cluster. Owns desired state (what should be running,
under what name), persists it to SQLite so it survives restarts, talks to
the Scheduler to actually place workloads, and handles failover when a
node goes down.

The Manager never talks to Docker or to a Worker directly — everything
goes through the Scheduler. This is what the frontend's buttons call.

## Files

- `db.py` — SQLite persistence: one `workloads` table mapping
  `name -> spec, node_id, container_id, status`.
- `manager.py` — core `Manager` class: `deploy`, `stop`, `remove`, `list`,
  and `handle_node_down` (failover).
- `api.py` — Flask REST API, the actual surface the frontend hits.

## Run it

```bash
pip install -r requirements.txt
SCHEDULER_URL=http://localhost:7000 python api.py
```

This creates `manager_state.db` in the working directory on first run.

## Using it

```bash
# Deploy a workload — Manager calls the Scheduler, which picks a node
curl -X POST http://localhost:8000/deploy \
  -H 'Content-Type: application/json' \
  -d '{"name":"web-1","spec":{"image":"nginx:latest","ports":{"80/tcp":8080},"restart_policy":"always"}}'

# List everything the Manager knows about
curl http://localhost:8000/workloads

# Filter by node or status
curl "http://localhost:8000/workloads?node_id=slave-1&status=running"

# Stop / remove
curl -X POST http://localhost:8000/workloads/web-1/stop
curl -X DELETE http://localhost:8000/workloads/web-1

# Trigger failover manually (this is what your health monitor should call
# automatically once it detects a dead node via the heartbeat file)
curl -X POST http://localhost:8000/nodes/slave-1/down
```

## How failover works

1. Health monitor detects a node stopped sending heartbeats.
2. It calls `POST /nodes/<node_id>/down`.
3. Manager looks up every workload with `status='running'` and `node_id`
   matching the dead node.
4. For each one, it calls `deploy()` again with the *same stored spec* —
   this re-invokes the Scheduler, which (per its "prefer master" policy)
   will place it on whichever node is alive.
5. Each workload's row is updated with its new `node_id`/`container_id`.

Known limitation, worth stating outright in your report: if the **master**
is the one that goes down, there's nowhere to reschedule to — this is a
true 2-node setup, not N-node. Real Kubernetes solves this with 3+ control
plane nodes and quorum (etcd/Raft), which is out of scope here but a good
thing to mention if asked "how would you extend this."

## Wiring the frontend

Every button in your UI should map directly to one of these endpoints —
`/deploy`, `/workloads/<name>/stop`, `DELETE /workloads/<name>`,
`GET /workloads` for the live list. Nothing else needs to be built for
the frontend to be fully functional against this API.
