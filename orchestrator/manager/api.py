"""
api.py

This is what the frontend's buttons call. Every user-facing action —
deploy, stop, remove, view status — goes through here. The health
monitor also calls into this (POST /nodes/<node_id>/down) when it
detects a node has stopped responding, to trigger failover.

Run:
    SCHEDULER_URL=http://localhost:7000 python api.py
"""

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from manager import Manager, ManagerError

SCHEDULER_URL = os.environ.get("SCHEDULER_URL", "http://localhost:7000")
PORT = int(os.environ.get("MANAGER_PORT", 8000))

app = Flask(__name__)
CORS(app)
manager = Manager(scheduler_url=SCHEDULER_URL)


def error_response(e: Exception, code: int = 400):
    return jsonify({"error": str(e)}), code


@app.route("/manager/deploy", methods=["POST"])
def deploy():
    body = request.get_json(force=True)
    name = body.get("name")
    spec = body.get("spec")
    if not name or not spec:
        return error_response("body must include 'name' and 'spec'")
    try:
        workload = manager.deploy(name, spec)
        return jsonify(workload), 201
    except ManagerError as e:
        return error_response(e, 503)


@app.route("/manager/workloads/<name>/stop", methods=["POST"])
def stop(name):
    try:
        manager.stop(name)
        return jsonify({"status": "stopped"})
    except ManagerError as e:
        return error_response(e, 404 if "no workload" in str(e) else 500)


@app.route("/manager/workloads/<name>", methods=["DELETE"])
def remove(name):
    try:
        manager.remove(name)
        return jsonify({"status": "removed"})
    except ManagerError as e:
        return error_response(e, 404)


@app.route("/manager/workloads/<name>", methods=["GET"])
def get_workload(name):
    try:
        return jsonify(manager.get(name))
    except ManagerError as e:
        return error_response(e, 404)


@app.route("/manager/workloads", methods=["GET"])
def list_workloads():
    node_id = request.args.get("node_id")
    status = request.args.get("status")
    return jsonify(manager.list(node_id=node_id, status=status))


@app.route("/manager/nodes/<node_id>/down", methods=["POST"])
def node_down(node_id):
    """Called by the health monitor when it detects a node is unreachable."""
    results = manager.handle_node_down(node_id)
    return jsonify({"rescheduled": results})

import os

@app.route("/manager/logs", methods=["GET"])
def get_logs():
    try:
        log_file = os.path.join(
            os.path.dirname(__file__),
            "manager.log"
        )

        with open(log_file, "r") as f:
            lines = f.readlines()

        return jsonify(lines[-20:])

    except FileNotFoundError:
        return jsonify(["No logs available"])
    
@app.route("/manager/workloads/<name>/restart", methods=["POST"])
def restart(name):
    try:
        manager.restart(name)
        return jsonify({"status": "restarted"})
    except ManagerError as e:
        return error_response(e, 404 if "no workload" in str(e) else 500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
