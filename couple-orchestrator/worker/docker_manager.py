"""
docker_manager.py

Core Worker logic for the orchestrator. Runs identically on the master
node and the slave node — each node's Worker only ever touches the
Docker daemon on its own machine. The Scheduler (elsewhere) decides
*which* node a workload should run on; this module only knows how to
carry out container operations once told to.

Wraps the `docker` Python SDK (talks to the local Docker daemon over
the unix socket) and exposes a small, orchestrator-friendly API.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import docker
from docker.errors import ImageNotFound, NotFound, APIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s %(message)s")
logger = logging.getLogger("worker")


@dataclass
class ContainerSpec:
    """Everything needed to run a container — the unit of work a Scheduler hands to a Worker."""
    image: str
    name: Optional[str] = None
    command: Optional[str] = None
    env: dict = field(default_factory=dict)
    ports: dict = field(default_factory=dict)          # {"container_port/tcp": host_port}
    volumes: dict = field(default_factory=dict)         # {"/host/path": {"bind": "/container/path", "mode": "rw"}}
    cpu_limit: Optional[float] = None                   # number of CPUs, e.g. 0.5
    mem_limit: Optional[str] = None                     # e.g. "256m", "1g"
    restart_policy: str = "no"                          # "no" | "on-failure" | "always" | "unless-stopped"
    network: Optional[str] = None


class WorkerError(Exception):
    """Raised for any worker-level failure, wrapping the underlying Docker error."""


class Worker:
    """
    Manages the container lifecycle on a single node using the local Docker daemon.

    Usage:
        worker = Worker(node_id="slave-1")
        cid = worker.run(ContainerSpec(image="nginx:latest", name="web-1"))
        worker.stop(cid)
        worker.remove(cid)
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            raise WorkerError(f"[{node_id}] could not connect to Docker daemon: {e}")
        logger.info(f"worker started on node '{node_id}', connected to Docker daemon")

    # ---------- image ----------

    def pull_image(self, image: str) -> str:
        """Pulls an image (with tag) from the registry. Returns the image ID."""
        try:
            logger.info(f"pulling image {image}")
            img = self.client.images.pull(image)
            return img.id
        except APIError as e:
            raise WorkerError(f"failed to pull image {image}: {e}")

    def image_exists_locally(self, image: str) -> bool:
        try:
            self.client.images.get(image)
            return True
        except ImageNotFound:
            return False

    # ---------- container lifecycle ----------

    def create_container(self, spec: ContainerSpec):
        """Creates a container from a spec without starting it. Returns the container object."""
        if not self.image_exists_locally(spec.image):
            self.pull_image(spec.image)

        try:
            container = self.client.containers.create(
                image=spec.image,
                name=spec.name,
                command=spec.command,
                environment=spec.env,
                ports=spec.ports,
                volumes=spec.volumes,
                network=spec.network,
                restart_policy={"Name": spec.restart_policy},
                nano_cpus=int(spec.cpu_limit * 1e9) if spec.cpu_limit else None,
                mem_limit=spec.mem_limit,
                detach=True,
            )
            logger.info(f"created container {container.short_id} ({spec.name or spec.image})")
            return container
        except APIError as e:
            raise WorkerError(f"failed to create container from {spec.image}: {e}")

    def start_container(self, container_id: str) -> None:
        container = self._get(container_id)
        try:
            print("a")
            container.start()
            print("b")
            logger.info(f"started container {container.short_id}")
        except APIError as e:
            print(f"failed to start container {container_id}: {e}")
            raise WorkerError(f"failed to start container {container_id}: {e}")

    def run(self, spec: ContainerSpec) -> str:
        """Convenience: pull (if needed) + create + start in one call. Returns the container ID."""
        container = self.create_container(spec)
        self.start_container(container.id)
        return container.id

    def stop_container(self, container_id: str, timeout: int = 10) -> None:
        container = self._get(container_id)
        try:
            container.stop(timeout=timeout)
            logger.info(f"stopped container {container.short_id}")
        except APIError as e:
            raise WorkerError(f"failed to stop container {container_id}: {e}")

    def restart_container(self, container_id: str, timeout: int = 10) -> None:
        container = self._get(container_id)
        try:
            container.restart(timeout=timeout)
            logger.info(f"restarted container {container.short_id}")
        except APIError as e:
            raise WorkerError(f"failed to restart container {container_id}: {e}")

    def remove_container(self, container_id: str, force: bool = False) -> None:
        container = self._get(container_id)
        try:
            container.remove(force=force)
            logger.info(f"removed container {container.short_id}")
        except APIError as e:
            raise WorkerError(f"failed to remove container {container_id}: {e}")

    # ---------- introspection ----------

    def get_status(self, container_id: str) -> dict:
        """Returns normalized status info the Scheduler/Manager can use for decisions."""
        container = self._get(container_id)
        container.reload()
        attrs = container.attrs
        state = attrs.get("State", {})
        return {
            "id": container.short_id,
            "name": container.name,
            "image": attrs.get("Config", {}).get("Image"),
            "status": container.status,               # running | exited | paused | restarting | dead
            "running": state.get("Running", False),
            "exit_code": state.get("ExitCode"),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "restart_count": attrs.get("RestartCount", 0),
            "health": state.get("Health", {}).get("Status") if "Health" in state else None,
        }

    def list_containers(self, all: bool = True) -> list:
        """Lists containers on this node. Mirrors what `kubectl get pods` would show for a node."""
        containers = self.client.containers.list(all=all)
        return [
            {
                "id": c.short_id,
                "name": c.name,
                "image": c.attrs.get("Config", {}).get("Image"),
                "status": c.status,
            }
            for c in containers
        ]

    def get_logs(self, container_id: str, tail: int = 100) -> str:
        container = self._get(container_id)
        try:
            return container.logs(tail=tail).decode("utf-8", errors="replace")
        except APIError as e:
            raise WorkerError(f"failed to fetch logs for {container_id}: {e}")

    def exec_in_container(self, container_id: str, cmd: str) -> str:
        """Runs a one-off command inside a running container (like `kubectl exec`)."""
        container = self._get(container_id)
        try:
            result = container.exec_run(cmd)
            return result.output.decode("utf-8", errors="replace")
        except APIError as e:
            raise WorkerError(f"exec failed in {container_id}: {e}")

    # ---------- self-healing ----------

    def ensure_running(self, spec: ContainerSpec, container_id: Optional[str] = None) -> str:
        """
        Idempotent reconciliation step: if the container exists and is running, do nothing.
        If it exists but crashed, restart it. If it doesn't exist, create and run it.
        This is the primitive a reconciliation loop calls repeatedly (see reconcile_loop.py).
        """
        if container_id:
            try:
                status = self.get_status(container_id)
                if status["running"]:
                    return container_id
                logger.warning(f"container {container_id} not running (status={status['status']}), restarting")
                self.start_container(container_id)
                return container_id
            except WorkerError:
                logger.warning(f"container {container_id} missing, recreating from spec")

        return self.run(spec)

    # ---------- cleanup ----------

    def prune_stopped(self) -> list:
        """Removes all stopped containers on this node. Returns list of removed container IDs."""
        result = self.client.containers.prune()
        removed = result.get("ContainersDeleted") or []
        logger.info(f"pruned {len(removed)} stopped container(s)")
        return removed

    # ---------- internal ----------

    def _get(self, container_id: str):
        try:
            return self.client.containers.get(container_id)
        except NotFound:
            raise WorkerError(f"container {container_id} not found on node '{self.node_id}'")
