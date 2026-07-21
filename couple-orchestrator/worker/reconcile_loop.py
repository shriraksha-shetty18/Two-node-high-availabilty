"""
reconcile_loop.py

Kubernetes' core idea isn't "run this container once" — it's "keep this
container running, forever, without being asked again." This loop is what
makes the Worker self-healing: it re-checks desired state against actual
state on an interval and corrects drift.

The Scheduler decides *what* should run on this node (desired state) and
hands the Worker a list of ContainerSpecs. This loop keeps them alive.

Run:
    NODE_ID=slave-1 python reconcile_loop.py
"""

import os
import time
import logging

from docker_manager import Worker, ContainerSpec

logger = logging.getLogger("worker.reconcile")

NODE_ID = os.environ.get("NODE_ID", "node-1")
INTERVAL_SECONDS = int(os.environ.get("RECONCILE_INTERVAL", 10))


class ReconcileLoop:
    """
    Holds the desired-state list for this node and continuously enforces it.
    In a full system, `desired_state` would be populated by the Manager
    (e.g. read from a synced state file or pushed via the API) rather than
    hardcoded — this class only owns the enforcement loop itself.
    """

    def __init__(self, worker: Worker):
        self.worker = worker
        # maps a logical workload name -> (ContainerSpec, last known container_id)
        self.desired_state: dict[str, tuple[ContainerSpec, str | None]] = {}

    def set_desired(self, workload_name: str, spec: ContainerSpec):
        """Called by the Manager/Scheduler when a workload is scheduled onto this node."""
        existing_id = self.desired_state.get(workload_name, (None, None))[1]
        self.desired_state[workload_name] = (spec, existing_id)
        logger.info(f"desired state updated for '{workload_name}' -> {spec.image}")

    def remove_desired(self, workload_name: str):
        """Called when a workload is descheduled/deleted."""
        entry = self.desired_state.pop(workload_name, None)
        if entry and entry[1]:
            try:
                self.worker.stop_container(entry[1])
                self.worker.remove_container(entry[1])
            except Exception as e:
                logger.warning(f"cleanup failed for '{workload_name}': {e}")

    def tick(self):
        """One reconciliation pass over every desired workload on this node."""
        for name, (spec, container_id) in list(self.desired_state.items()):
            try:
                new_id = self.worker.ensure_running(spec, container_id)
                if new_id != container_id:
                    self.desired_state[name] = (spec, new_id)
            except Exception as e:
                logger.error(f"failed to reconcile '{name}': {e}")

    def run_forever(self, interval: int = INTERVAL_SECONDS):
        logger.info(f"reconcile loop started on node '{self.worker.node_id}' (every {interval}s)")
        while True:
            self.tick()
            time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [reconcile] %(levelname)s %(message)s")
    worker = Worker(node_id=NODE_ID)
    loop = ReconcileLoop(worker)

    # Example: in the real system this comes from the Manager, not hardcoded.
    # loop.set_desired("web", ContainerSpec(image="nginx:latest", name="web-1", restart_policy="always"))

    loop.run_forever()
