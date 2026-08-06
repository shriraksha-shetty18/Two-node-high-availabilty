"""
manager.py

The Manager is the brain of the cluster: it owns desired state (what
should be running, under what name), talks to the Scheduler to actually
place workloads, and reacts to node failures by rescheduling whatever
was running on a dead node.

It never talks to Docker or to a specific node's Worker directly — it
only ever goes through the Scheduler, same way kube's control loops
never bypass kube-scheduler to talk to a kubelet directly for placement.
"""

import logging
import threading
import os
import requests

import db
LOG_FILE = os.path.join(os.path.dirname(__file__), "manager.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [manager] %(levelname)s %(message)s"
)
logger = logging.getLogger("manager")

REQUEST_TIMEOUT = 10
HEALTH_POLL_INTERVAL = 5  # seconds between health checks


class ManagerError(Exception):
    pass


class HealthMonitor:
    """
    Periodically polls the Scheduler's /nodes/status endpoint. When a node
    that was previously alive becomes unreachable, triggers failover via
    Manager.handle_node_down().
    """

    def __init__(self, manager: "Manager", poll_interval: int = HEALTH_POLL_INTERVAL):
        self.manager = manager
        self.poll_interval = poll_interval
        self._alive: dict[str, bool] = {}  # node_id -> was_alive_on_last_check
        self._stop_event = threading.Event()
        
        self._thread = threading.Thread(target=self._run, daemon=True, name="health-monitor")

    def start(self):
        logger.info(f"health monitor starting (poll every {self.poll_interval}s)")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        
    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._check()
            except Exception as e:
                logger.error(f"health monitor check failed: {e}")
            self._stop_event.wait(self.poll_interval)

    def _check(self):
        try:
            r = requests.get(
                f"{self.manager.scheduler_url}/nodes/status",
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            statuses = r.json()
        except requests.RequestException:
            logger.warning("health monitor cannot reach scheduler \u2014 skipping this cycle")
            return

        for node_id, info in statuses.items():
            was_alive = self._alive.get(node_id, True)  # assume alive on first sight
            is_alive = info.get("alive", False)

            if was_alive and not is_alive:
                logger.warning(f"health monitor detected node '{node_id}' went down")
                self.manager.handle_node_down(node_id)

            self._alive[node_id] = is_alive


class Manager:
    def __init__(self, scheduler_url: str, db_path: str = db.DB_PATH, health_poll_interval: int = HEALTH_POLL_INTERVAL):
        self.scheduler_url = scheduler_url.rstrip("/")
        self.db_path = db_path
        db.init_db(db_path)
        self._health_monitor = HealthMonitor(self, poll_interval=health_poll_interval)
        self._health_monitor.start()

    # ---------- workload lifecycle ----------

    def deploy(self, name: str, spec: dict) -> dict:
        """
        Registers desired state for a named workload and asks the Scheduler
        to place it. If a workload with this name already exists, this
        redeploys it (useful for both updates and manual reschedule).
        """
        db.upsert_workload(name, spec, status="pending", path=self.db_path)
        try:
            r = requests.post(f"{self.scheduler_url}/schedule", json=spec, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            result = r.json()
        except requests.RequestException as e:
            db.upsert_workload(name, spec, status="failed", path=self.db_path)
            raise ManagerError(f"failed to schedule '{name}': {e}")

        db.upsert_workload(
            name, spec,
            node_id=result["node_id"],
            container_id=result["container_id"],
            status="running",
            path=self.db_path,
        )
        logger.info(f"deployed '{name}' -> node={result['node_id']} container={result['container_id']}")
        return db.get_workload(name, path=self.db_path)

    def stop(self, name: str) -> None:
        workload = self._require(name)
        if workload["node_id"] and workload["container_id"]:
            try:
                r = requests.post(
                    f"{self.scheduler_url}/containers/{workload['node_id']}/{workload['container_id']}/stop",
                    timeout=REQUEST_TIMEOUT,
                )
                r.raise_for_status()
            except requests.RequestException as e:
                raise ManagerError(f"failed to stop '{name}': {e}")
        db.upsert_workload(name, workload["spec"], node_id=workload["node_id"],
                            container_id=workload["container_id"], status="stopped", path=self.db_path)
        logger.info(f"stopped '{name}'")
        
    def restart(self, name: str) -> None:
        workload = self._require(name)

        if workload["node_id"] and workload["container_id"]:
            try:
                r = requests.post(
                    f"{self.scheduler_url}/containers/{workload['node_id']}/{workload['container_id']}/restart",
                    timeout=REQUEST_TIMEOUT,
                )
                r.raise_for_status()
            except requests.RequestException as e:
                raise ManagerError(f"failed to restart '{name}': {e}")

        db.upsert_workload(
            name,
            workload["spec"],
            node_id=workload["node_id"],
            container_id=workload["container_id"],
            status="running",
            path=self.db_path,
        )

        logger.info(f"restarted '{name}'")

    def remove(self, name: str) -> None:
        workload = self._require(name)
        if workload["node_id"] and workload["container_id"]:
            try:
                r = requests.delete(
                    f"{self.scheduler_url}/containers/{workload['node_id']}/{workload['container_id']}",
                    params={"force": "true"},
                    timeout=REQUEST_TIMEOUT,
                )
                r.raise_for_status()
            except requests.RequestException as e:
                logger.warning(f"remove call failed for '{name}' (continuing to drop desired state): {e}")
        db.delete_workload(name, path=self.db_path)
        logger.info(f"removed '{name}' from desired state")

    def get(self, name: str) -> dict:
        return self._require(name)

    def list(self, node_id: str = None, status: str = None) -> list:
        return db.list_workloads(node_id=node_id, status=status, path=self.db_path)

    # ---------- failover ----------

    def handle_node_down(self, node_id: str) -> list:
        """
        Called when the health monitor reports a node is dead. Reschedules
        every 'running' workload that was on that node. Because the
        Scheduler's policy prefers the master, workloads from a dead slave
        will land on the master automatically as long as it has capacity;
        workloads from a dead master have nowhere to go until it recovers
        (this 2-node setup has no third node to fall back to).
        """
        affected = db.list_workloads(node_id=node_id, status="running", path=self.db_path)
        if not affected:
            logger.info(f"node '{node_id}' reported down, no running workloads to reschedule")
            return []

        logger.warning(f"node '{node_id}' reported down, rescheduling {len(affected)} workload(s)")
        results = []
        for workload in affected:
            try:
                result = self.deploy(workload["name"], workload["spec"])
                results.append({"name": workload["name"], "status": "rescheduled", "new_node": result["node_id"]})
            except ManagerError as e:
                db.upsert_workload(workload["name"], workload["spec"], status="failed", path=self.db_path)
                results.append({"name": workload["name"], "status": "failed", "error": str(e)})
                logger.error(f"failed to reschedule '{workload['name']}': {e}")
        return results

    # ---------- internal ----------

    def _require(self, name: str) -> dict:
        workload = db.get_workload(name, path=self.db_path)
        if not workload:
            raise ManagerError(f"no workload named '{name}'")
        return workload
