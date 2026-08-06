"""
scheduler.py

Decides WHICH node a workload runs on, then hands it off to that node's
Worker API to actually run it. The Scheduler itself never touches Docker —
that's the Worker's job. This keeps the same separation of concerns
Kubernetes has between kube-scheduler (decides) and kubelet (executes).

Policy for this 2-node setup: prefer the master. Only place on the slave
if the master is dead (unreachable) or busy (at/over its container
capacity). This is deliberately simple — with only two nodes, a fancier
bin-packing algorithm isn't worth the complexity for a college project,
but the strategy is isolated in `choose_node()` so it can be swapped later.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scheduler] %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")

HEALTH_TIMEOUT = 2      # seconds — health checks must be fast, a slow node should look "busy", not hang the scheduler
REQUEST_TIMEOUT = 10    # seconds — actual container operations (image pulls) can take longer


@dataclass
class NodeInfo:
    """Static info about a node the scheduler can place workloads on."""
    node_id: str
    role: str              # "master" | "slave"
    base_url: str          # e.g. "http://192.168.1.10:6000"
    capacity: int = 10      # max running containers before this node is considered "busy"


@dataclass
class WorkloadSpec:
    """Mirrors ContainerSpec from the Worker — this is the JSON body the Worker API expects."""
    image: str
    name: Optional[str] = None
    command: Optional[str] = None
    env: dict = field(default_factory=dict)
    ports: dict = field(default_factory=dict)
    volumes: dict = field(default_factory=dict)
    cpu_limit: Optional[float] = None
    mem_limit: Optional[str] = None
    restart_policy: str = "no"
    network: Optional[str] = None

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class SchedulerError(Exception):
    """Raised when no node is available to schedule onto, or placement fails outright."""


class Scheduler:
    def __init__(self, nodes: list[NodeInfo]):
        self.nodes = {n.node_id: n for n in nodes}
        self._master = next((n for n in nodes if n.role == "master"), None)
        self._slave = next((n for n in nodes if n.role == "slave"), None)
        if not self._master or not self._slave:
            raise SchedulerError("scheduler requires exactly one 'master' and one 'slave' node")

    # ---------- node health / load ----------

    def is_alive(self, node: NodeInfo) -> bool:
        """A node is alive if its Worker API responds to /health in time."""
        try:
            r = requests.get(f"{node.base_url}/health", timeout=HEALTH_TIMEOUT)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def current_load(self, node: NodeInfo) -> Optional[int]:
        """Number of currently-running containers on a node. None if unreachable."""
        try:
            r = requests.get(f"{node.base_url}/containers", params={"all": "false"}, timeout=HEALTH_TIMEOUT)
            r.raise_for_status()
            return len(r.json())
        except requests.RequestException:
            return None

    def is_busy(self, node: NodeInfo) -> bool:
        load = self.current_load(node)
        return load is None or load >= node.capacity

    # ---------- placement ----------

    def choose_node(self) -> NodeInfo:
        """
        Placement policy: prefer master. Fall back to slave only if the
        master is dead or busy. Raises SchedulerError if neither node
        can take the workload.
        """
        if self.is_alive(self._master) and not self.is_busy(self._master):
            logger.info(f"placing on master '{self._master.node_id}'")
            return self._master

        reason = "unreachable" if not self.is_alive(self._master) else "at capacity"
        logger.warning(f"master is {reason}, checking slave")

        if self.is_alive(self._slave) and not self.is_busy(self._slave):
            logger.info(f"placing on slave '{self._slave.node_id}'")
            return self._slave

        raise SchedulerError("no available node: both master and slave are dead or at capacity")

    # ---------- scheduling ----------

    def schedule(self, spec: WorkloadSpec) -> dict:
        """
        Picks a node and forwards the workload to that node's Worker API.
        If placement on the chosen node fails mid-flight (e.g. it died
        between the health check and the actual request), retries once
        on the other node before giving up.
        """
        node = self.choose_node()
        try:
            return self._place_on(node, spec)
        except SchedulerError:
            fallback = self._slave if node.node_id == self._master.node_id else self._master
            logger.warning(f"placement on '{node.node_id}' failed, retrying on '{fallback.node_id}'")
            if not self.is_alive(fallback):
                raise SchedulerError(f"placement on '{node.node_id}' failed and fallback '{fallback.node_id}' is also unavailable")
            return self._place_on(fallback, spec)

    def _place_on(self, node: NodeInfo, spec: WorkloadSpec) -> dict:
        try:
            r = requests.post(f"{node.base_url}/containers", json=spec.to_json(), timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            result = r.json()
            return {"node_id": node.node_id, "container_id": result["container_id"]}
        except requests.RequestException as e:
            raise SchedulerError(f"failed to place workload on '{node.node_id}': {e}")

    # ---------- operations that need to know which node a container is on ----------
    # (In a full system the Manager tracks node placement per container; these
    # helpers assume the caller already knows which node, mirroring how the
    # Worker API itself is node-scoped.)

    def stop(self, node_id: str, container_id: str) -> None:
        node = self._require_node(node_id)
        r = requests.post(f"{node.base_url}/containers/{container_id}/stop", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()

    def remove(self, node_id: str, container_id: str, force: bool = False) -> None:
        node = self._require_node(node_id)
        r = requests.delete(f"{node.base_url}/containers/{container_id}", params={"force": str(force).lower()}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()

    def status(self, node_id: str, container_id: str) -> dict:
        node = self._require_node(node_id)
        r = requests.get(f"{node.base_url}/containers/{container_id}", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _require_node(self, node_id: str) -> NodeInfo:
        node = self.nodes.get(node_id)
        if not node:
            raise SchedulerError(f"unknown node '{node_id}'")
        return node
        
    def restart(self, node_id: str, container_id: str) -> None:
        node = self._require_node(node_id)
        r = requests.post(
            f"{node.base_url}/containers/{container_id}/restart",
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
