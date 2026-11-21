# Lightweight Two-Node High Availability Framework

A lightweight high-availability framework that provides workload management, automated failover, and service continuity using a two-node architecture.

The project combines Keepalived, Docker, and a custom Python-based workload orchestrator with a React dashboard to manage workloads across two nodes.

## 1. Project Overview

Traditional high-availability clustering solutions can require additional infrastructure and quorum-based coordination.

This project explores a lightweight alternative using two nodes:

- **Node A:** Primary node under normal operating conditions.
- **Node B:** Backup node that can take over when Node A becomes unavailable.

The framework uses a Virtual IP (VIP) managed by Keepalived for network-level failover and a custom orchestrator for workload scheduling and recovery.

## 2. Key Features

- Two-node high-availability architecture.
- VIP failover using Keepalived and VRRP.
- Docker-based workload deployment.
- Automated workload scheduling across nodes.
- Health monitoring of worker nodes.
- Workload recovery after node failure.
- SQLite-based workload state persistence.
- Database synchronization between nodes.
- React-based management dashboard.
- Worker reconciliation for restarting stopped workloads.

## 3. System Architecture

The framework consists of three major components.

### A. High Availability Layer

Implemented using Keepalived and VRRP.

- Monitors node availability.
- Manages ownership of the Virtual IP.
- Transfers VIP ownership during failover.
- Executes notification scripts during MASTER, BACKUP, and FAULT state transitions.
- Synchronizes workload database state between nodes.

### B. Workload Orchestration Layer

The orchestration layer contains three components:

**Manager**
- Maintains workload information.
- Stores desired workload state using SQLite.
- Communicates with the Scheduler.
- Handles workload recovery after node failure.

**Scheduler**
- Selects the appropriate node for workload deployment.
- Checks worker health and workload capacity.
- Forwards deployment requests to the selected Worker.
- Retries placement on the alternate node when necessary.

**Worker**
- Communicates with the local Docker daemon.
- Pulls container images.
- Creates, starts, stops, and removes containers.
- Monitors actual workload state and reconciles it with desired state.

### C. Frontend Layer

A React-based dashboard provides an interface for:

- Viewing node and worker status.
- Deploying workloads.
- Monitoring running workloads.
- Managing deployed containers.
- Observing failover and workload recovery.

### Architecture Flow

```text
                 User
                  |
                  v
          React Dashboard
                  |
                  v
             Manager
             Port 8000
                  |
                  v
             Scheduler
             Port 7000
                  |
          +-------+-------+
          |               |
          v               v
       Worker A        Worker B
       Port 6000       Port 6001
          |               |
          v               v
       Docker A         Docker B

       Node A  <---->  Node B
              Keepalived
              VRRP / VIP
              Database Sync
```

## 4. Technologies Used

| Component | Technology |
|---|---|
| Frontend | React.js |
| Backend | Python, Flask |
| Containerization | Docker |
| High Availability | Keepalived, VRRP |
| Database | SQLite |
| Database Synchronization | Rsync, SSH |
| Communication | REST APIs |
| Operating System | Linux |

## 5. Repository Structure

```text
Two-node-high-availability/
│
├── demo-app/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── README.md
│
├── keepalived/
│   ├── keepalived-master.conf
│   ├── keepalived-slave.conf
│   ├── ha.env.example
│   ├── db_sync_push.sh
│   ├── notify_master.sh
│   ├── notify_backup.sh
│   ├── notify_fault.sh
│   └── README.md
│
├── orchestrator/
│   ├── manager/
│   ├── scheduler/
│   └── worker/
│
├── results/
│   ├── apache_ab.png
│   └── apache_ab.txt
│
├── screenshots/
│
├── .gitignore
└── README.md
```

## 6. Installation and Configuration

### Prerequisites

Install the following on the respective nodes:

- Linux operating system.
- Python 3.
- Docker Engine.
- Keepalived.
- Node.js and npm (for frontend development).
- Rsync and SSH.

Ensure both nodes can communicate over the network.

### Clone the Repository

```bash
git clone https://github.com/shriraksha-shetty18/Two-node-high-availabilty.git
cd Two-node-high-availabilty
```

### Configure the Keepalived Environment

Create a local environment configuration using the example:

```bash
cp keepalived/ha.env.example keepalived/ha.env
```

Edit `ha.env` with the appropriate node addresses, SSH configuration, and other required settings.

Configure the MASTER and BACKUP Keepalived configuration files with the appropriate network interface, virtual router ID, priorities, and shared authentication settings.

The configuration must be adapted to the network interfaces and Linux users on each node.

Refer to `keepalived/README.md` for additional configuration details.

### Install Backend Dependencies

Install the Manager dependencies:

```bash
cd orchestrator/manager
pip install -r requirements.txt
```

Install the Scheduler dependencies:

```bash
cd ../scheduler
pip install -r requirements.txt
```

Install the Worker dependencies on both nodes:

```bash
cd ../worker
pip install -r requirements.txt
```

### Start the Worker Services

On Node A:

```bash
cd orchestrator/worker
NODE_ID=master-1 PORT=6000 python api.py
```

On Node B:

```bash
cd orchestrator/worker
NODE_ID=slave-1 PORT=6001 python api.py
```

### Start the Scheduler

On the node hosting the Scheduler:

```bash
cd orchestrator/scheduler

MASTER_URL=http://NODE_A_IP:6000 \
SLAVE_URL=http://NODE_B_IP:6001 \
python api.py
```

Replace the placeholder IP addresses with the actual node addresses.

### Start the Manager

```bash
cd orchestrator/manager

SCHEDULER_URL=http://localhost:7000 python api.py
```

The Manager API listens on port 8000.

### Start the Frontend

```bash
cd frontend
npm install
npm start
```

The React development server starts on its configured local port.

### Configure High Availability

Configure and enable Keepalived on both nodes using the provided configuration files and notification scripts.

Ensure the following are configured correctly:

- VRRP interface and virtual router settings.
- MASTER and BACKUP priorities.
- VIP address.
- Notification script permissions.
- SSH authentication between nodes.
- Database synchronization paths.

Refer to the Keepalived documentation in the `keepalived/` directory.

## 7. Failover Mechanism

The framework uses two complementary mechanisms.

### Network-Level Failover

1. Keepalived monitors the availability of the nodes.
2. When the MASTER node becomes unavailable, VRRP initiates a state transition.
3. The BACKUP node takes ownership of the Virtual IP.
4. The MASTER notification scripts start the required HA services and synchronize workload state.

### Workload-Level Recovery

1. Node health monitoring detects a failed worker.
2. The Manager identifies workloads associated with the failed node.
3. The Scheduler selects an available node.
4. The Worker on the selected node deploys the workload.
5. The Manager updates the workload information with the new node and container details.

This separates network-level failover from application workload recovery.

## 8. Experimental Results

The framework was evaluated through failover experiments and Apache Benchmark testing.

### Failover Performance

| Metric | Observed Result |
|---|---:|
| VIP failover time | 2.08 seconds |
| Approximate orchestrator recovery time | 8 seconds |
| Failure detection component of orchestrator recovery | Approximately 5 seconds |
| Workload rescheduling component | Approximately 3 seconds |

### Apache Benchmark Results

**Normal operation**

| Metric | Result |
|---|---:|
| Total requests | 1000 |
| Concurrency | 20 |
| Failed requests | 0 |
| Requests per second | 267.70 |
| Average response time | 74.7 ms |

**During failover**

| Metric | Result |
|---|---:|
| Total requests | 500 |
| Concurrency | 10 |
| Failed requests | 0 |
| Requests per second | 114.46 |
| Average response time | 87.369 ms |

The two benchmark tests used different request counts and concurrency levels, so their throughput values should not be treated as a direct like-for-like comparison.

## 9. Screenshots

The `screenshots/` directory contains implementation screenshots demonstrating:

- Both nodes reporting healthy status.
- Dashboard workload deployment.
- Running demo application.
- VIP ownership on Node A.
- Manager workload rescheduling.
- Scheduler and Worker health.
- Dashboard failover behaviour.

## 10. Limitations

- The architecture consists of only two nodes and does not implement quorum-based consensus.
- Network partitioning can introduce split-brain risk.
- Periodic database synchronization may result in stale backup state.
- Failback behaviour is not fully automated.
- The scheduler uses container count as a capacity indicator rather than detailed CPU and memory resource allocation.
- Performance measurements are based on the implemented experimental setup and do not establish long-term production availability.

## 11. Future Enhancements

- Introduce fencing mechanisms to reduce split-brain risk.
- Improve workload state consistency.
- Implement automated failback.
- Add CPU and memory-aware scheduling.
- Improve monitoring and observability.
- Evaluate the framework under larger workloads and sustained traffic.

## 12. Conclusion

This project demonstrates a lightweight two-node high-availability framework integrating network-level failover, container orchestration, workload recovery, and a web-based management dashboard.

The implementation demonstrates how Keepalived, Docker, and a custom Python-based orchestration layer can work together to provide service continuity with relatively minimal infrastructure.
