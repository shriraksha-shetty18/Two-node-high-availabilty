# Worker

Runs identically on the master and the slave node. Each node's Worker only
ever talks to the Docker daemon **on its own machine** — the Scheduler
decides *which* node a workload runs on; the Worker just carries it out
locally, over HTTP.

## Files

- `docker_manager.py` — core `Worker` class: pull, create, start, stop,
  restart, remove, inspect, logs, exec. This is the part that talks to Docker.
- `api.py` — Flask REST API wrapping the Worker, so the Manager/Scheduler
  (possibly on the other node) can command it over HTTP.
- `reconcile_loop.py` — the self-healing loop. Kubernetes' core trick isn't
  "start this container" — it's "keep this container running forever." This
  polls desired state vs actual state and restarts anything that died.

## Run it

```bash
pip install -r requirements.txt

# On the slave:
NODE_ID=slave-1 PORT=6001 python api.py

# On the master (its own local worker):
NODE_ID=master-1 PORT=6000 python api.py
```

## Talking to a worker (from the Scheduler, or curl for testing)

```bash
# Pull an image
curl -X POST http://slave-host:6001/images/pull -d '{"image":"nginx:latest"}' -H 'Content-Type: application/json'

# Run a container (pull + create + start)
curl -X POST http://slave-host:6001/containers \
  -H 'Content-Type: application/json' \
  -d '{"image":"nginx:latest","name":"web-1","ports":{"80/tcp":8080},"restart_policy":"always"}'

# List containers on this node
curl http://slave-host:6001/containers

# Check one container's status
curl http://slave-host:6001/containers/web-1

# Stop / restart / remove
curl -X POST http://slave-host:6001/containers/web-1/stop
curl -X POST http://slave-host:6001/containers/web-1/restart
curl -X DELETE http://slave-host:6001/containers/web-1?force=true

# Logs
curl http://slave-host:6001/containers/web-1/logs?tail=50
```

## Self-healing

`reconcile_loop.py` is what makes this an orchestrator worker rather than a
one-shot script runner. The Manager pushes desired state (which workloads
should exist on this node); the loop checks every N seconds and restarts
anything that's supposed to be running but isn't:

```python
from docker_manager import Worker, ContainerSpec
from reconcile_loop import ReconcileLoop

worker = Worker(node_id="slave-1")
loop = ReconcileLoop(worker)
loop.set_desired("web", ContainerSpec(image="nginx:latest", name="web-1", restart_policy="always"))
loop.run_forever()
```

## Where this plugs into the rest of the system

- **Scheduler → Worker**: scheduler calls the Worker's REST API (`/containers` POST)
  to place a workload on a chosen node.
- **Manager → Worker**: manager reads `/containers` and `/containers/<id>` to
  know current cluster state, and calls `/containers/<id>/stop` etc. for
  user-triggered actions from the frontend.
- **Health monitor**: separate from this — the heartbeat file your health
  monitor watches with `inotifywait` is a different signal (node liveness).
  `/health` here answers "is this node's worker API responsive," which is a
  useful second signal alongside the heartbeat file.
