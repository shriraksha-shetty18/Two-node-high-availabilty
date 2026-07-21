"""
api.py

Exposes the Scheduler over HTTP. The Manager (and eventually the frontend,
via the Manager) calls POST /schedule with a workload spec and doesn't
need to know or care whether it landed on the master or the slave — that
decision is entirely internal to the Scheduler.

Run:
    MASTER_URL=http://192.168.1.10:6000 SLAVE_URL=http://192.168.1.20:6001 python api.py
"""

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from scheduler import Scheduler, NodeInfo, WorkloadSpec, SchedulerError

MASTER_URL = os.environ.get("MASTER_URL", "http://localhost:6000")
SLAVE_URL = os.environ.get("SLAVE_URL", "http://localhost:6001")
PORT = int(os.environ.get("SCHEDULER_PORT", 7000))

app = Flask(__name__)
CORS(app)
scheduler = Scheduler([
    NodeInfo(node_id="master-1", role="master", base_url=MASTER_URL, capacity=int(os.environ.get("MASTER_CAPACITY", 10))),
    NodeInfo(node_id="slave-1", role="slave", base_url=SLAVE_URL, capacity=int(os.environ.get("SLAVE_CAPACITY", 10))),
])


def error_response(e: Exception, code: int = 400):
    return jsonify({"error": str(e)}), code


@app.route("/schedule", methods=["POST"])
def schedule():
    body = request.get_json(force=True)
    try:
        spec = WorkloadSpec(
            image=body["image"],
            name=body.get("name"),
            command=body.get("command"),
            env=body.get("env", {}),
            ports=body.get("ports", {}),
            volumes=body.get("volumes", {}),
            cpu_limit=body.get("cpu_limit"),
            mem_limit=body.get("mem_limit"),
            restart_policy=body.get("restart_policy", "no"),
            network=body.get("network"),
        )
        result = scheduler.schedule(spec)
        return jsonify(result), 201
    except KeyError as e:
        return error_response(f"missing required field: {e}")
    except SchedulerError as e:
        return error_response(e, 503)


@app.route("/nodes/status", methods=["GET"])
def nodes_status():
    """Quick view of both nodes' health/load — handy for the frontend dashboard."""
    result = {}
    for node_id, node in scheduler.nodes.items():
        alive = scheduler.is_alive(node)
        result[node_id] = {
            "role": node.role,
            "alive": alive,
            "load": scheduler.current_load(node) if alive else None,
            "capacity": node.capacity,
        }
    return jsonify(result)


@app.route("/containers/<node_id>/<container_id>/stop", methods=["POST"])
def stop(node_id, container_id):
    try:
        scheduler.stop(node_id, container_id)
        return jsonify({"status": "stopped"})
    except SchedulerError as e:
        return error_response(e, 500)


@app.route("/containers/<node_id>/<container_id>", methods=["DELETE"])
def remove(node_id, container_id):
    force = request.args.get("force", "false") == "true"
    try:
        scheduler.remove(node_id, container_id, force=force)
        return jsonify({"status": "removed"})
    except SchedulerError as e:
        return error_response(e, 500)


@app.route("/containers/<node_id>/<container_id>", methods=["GET"])
def status(node_id, container_id):
    try:
        return jsonify(scheduler.status(node_id, container_id))
    except SchedulerError as e:
        return error_response(e, 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
