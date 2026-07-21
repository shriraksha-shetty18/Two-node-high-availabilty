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
DB_PATH = os.environ.get("MANAGER_DB_PATH")  # falls back to db.DB_PATH default if unset

app = Flask(__name__)
CORS(app)  # allows the browser-based frontend (served from a different origin) to call this API
manager = Manager(scheduler_url=SCHEDULER_URL, db_path=DB_PATH) if DB_PATH else Manager(scheduler_url=SCHEDULER_URL)


def error_response(e: Exception, code: int = 400):
    return jsonify({"error": str(e)}), code


@app.route("/deploy", methods=["POST"])
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


@app.route("/workloads/<name>/stop", methods=["POST"])
def stop(name):
    try:
        manager.stop(name)
        return jsonify({"status": "stopped"})
    except ManagerError as e:
        return error_response(e, 404 if "no workload" in str(e) else 500)


@app.route("/workloads/<name>", methods=["DELETE"])
def remove(name):
    try:
        manager.remove(name)
        return jsonify({"status": "removed"})
    except ManagerError as e:
        return error_response(e, 404)


@app.route("/workloads/<name>", methods=["GET"])
def get_workload(name):
    try:
        return jsonify(manager.get(name))
    except ManagerError as e:
        return error_response(e, 404)


@app.route("/workloads", methods=["GET"])
def list_workloads():
    node_id = request.args.get("node_id")
    status = request.args.get("status")
    return jsonify(manager.list(node_id=node_id, status=status))


@app.route("/nodes/<node_id>/down", methods=["POST"])
def node_down(node_id):
    """Called by the health monitor when it detects a node is unreachable."""
    results = manager.handle_node_down(node_id)
    return jsonify({"rescheduled": results})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
