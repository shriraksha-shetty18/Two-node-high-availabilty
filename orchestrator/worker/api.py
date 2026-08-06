"""
api.py

Exposes the Worker over HTTP so the Manager/Scheduler can command it —
including across nodes (the master's scheduler calling the slave's worker).
The master's own worker can be called the same way, on localhost, keeping
both nodes symmetric.

Run:
    NODE_ID=slave-1 PORT=6001 python api.py
"""

import os
import logging
from flask import Flask, request, jsonify

from docker_manager import Worker, ContainerSpec, WorkerError

NODE_ID = os.environ.get("NODE_ID", "node-1")
PORT = int(os.environ.get("PORT", 6001))

app = Flask(__name__)
worker = Worker(node_id=NODE_ID)
logger = logging.getLogger("worker.api")


def error_response(e: Exception, code: int = 400):
    return jsonify({"error": str(e)}), code


@app.route("/health", methods=["GET"])
def health():
    """Liveness endpoint — the master's health monitor can poll this directly,
    or this node can push its own heartbeat elsewhere (see heartbeat.py)."""
    return jsonify({"node_id": NODE_ID, "status": "alive"})


@app.route("/images/pull", methods=["POST"])
def pull_image():
    body = request.get_json(force=True)
    image = body.get("image")
    if not image:
        return error_response("missing 'image'")
    try:
        image_id = worker.pull_image(image)
        return jsonify({"image_id": image_id})
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers", methods=["POST"])
def run_container():
    """Create + start a container in one call. Body mirrors ContainerSpec fields."""
    body = request.get_json(force=True)
    try:
        spec = ContainerSpec(
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
        container_id = worker.run(spec)
        return jsonify({"container_id": container_id}), 201
    except KeyError as e:
        return error_response(f"missing required field: {e}")
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers", methods=["GET"])
def list_containers():
    return jsonify(worker.list_containers(all=request.args.get("all", "true") == "true"))


@app.route("/containers/<container_id>", methods=["GET"])
def get_container(container_id):
    try:
        return jsonify(worker.get_status(container_id))
    except WorkerError as e:
        return error_response(e, 404)


@app.route("/containers/<container_id>/start", methods=["POST"])
def start_container(container_id):
    try:
        worker.start_container(container_id)
        return jsonify({"status": "started"})
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers/<container_id>/stop", methods=["POST"])
def stop_container(container_id):
    timeout = int(request.args.get("timeout", 10))
    try:
        worker.stop_container(container_id, timeout=timeout)
        return jsonify({"status": "stopped"})
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers/<container_id>/restart", methods=["POST"])
def restart_container(container_id):
    try:
        worker.restart_container(container_id)
        return jsonify({"status": "restarted"})
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers/<container_id>", methods=["DELETE"])
def remove_container(container_id):
    force = request.args.get("force", "false") == "true"
    try:
        worker.remove_container(container_id, force=force)
        return jsonify({"status": "removed"})
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers/<container_id>/logs", methods=["GET"])
def get_logs(container_id):
    tail = int(request.args.get("tail", 100))
    try:
        return jsonify({"logs": worker.get_logs(container_id, tail=tail)})
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers/<container_id>/exec", methods=["POST"])
def exec_in_container(container_id):
    body = request.get_json(force=True)
    cmd = body.get("cmd")
    if not cmd:
        return error_response("missing 'cmd'")
    try:
        output = worker.exec_in_container(container_id, cmd)
        return jsonify({"output": output})
    except WorkerError as e:
        return error_response(e, 500)


@app.route("/containers/prune", methods=["POST"])
def prune():
    removed = worker.prune_stopped()
    return jsonify({"removed": removed})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
