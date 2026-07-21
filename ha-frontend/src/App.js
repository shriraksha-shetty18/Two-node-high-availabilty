import React, { useState, useEffect } from 'react';
import axios from 'axios';

const MANAGER_URL = 'http://192.168.195.3:8000';
const SCHEDULER_URL = 'http://192.168.195.3:7000';

const styles = {
  app: {
    fontFamily: 'Arial, sans-serif',
    background: '#1a1a2e',
    minHeight: '100vh',
    color: 'white',
    padding: '20px',
  },
  header: {
    textAlign: 'center',
    color: '#00d4ff',
    fontSize: '28px',
    marginBottom: '10px',
  },
  subtitle: {
    textAlign: 'center',
    color: '#888',
    fontSize: '12px',
    marginBottom: '30px',
  },
  nav: {
    display: 'flex',
    justifyContent: 'center',
    gap: '10px',
    marginBottom: '30px',
  },
  navBtn: (active) => ({
    padding: '10px 20px',
    background: active ? '#00d4ff' : '#16213e',
    color: active ? 'black' : 'white',
    border: 'none',
    borderRadius: '5px',
    cursor: 'pointer',
    fontWeight: active ? 'bold' : 'normal',
  }),
  card: {
    background: '#16213e',
    borderRadius: '10px',
    padding: '20px',
    border: '2px solid #0f3460',
    marginBottom: '20px',
  },
  nodeGrid: {
    display: 'flex',
    gap: '20px',
    justifyContent: 'center',
    marginBottom: '20px',
  },
  nodeCard: (status) => ({
    background: '#16213e',
    borderRadius: '10px',
    padding: '25px',
    width: '250px',
    textAlign: 'center',
    border: `2px solid ${status === 'alive' ? '#00b300' : '#cc0000'}`,
  }),
  statusBadge: (status) => ({
    background: status === 'alive' ? '#00b300' : '#cc0000',
    padding: '8px 15px',
    borderRadius: '5px',
    fontWeight: 'bold',
    display: 'inline-block',
    margin: '10px 0',
  }),
  vipBadge: {
    background: '#00d4ff',
    color: 'black',
    padding: '5px 10px',
    borderRadius: '5px',
    fontSize: '12px',
    fontWeight: 'bold',
    display: 'inline-block',
    marginTop: '10px',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  th: {
    background: '#0f3460',
    padding: '12px',
    textAlign: 'left',
    color: '#00d4ff',
  },
  td: {
    padding: '12px',
    borderBottom: '1px solid #0f3460',
  },
  btn: (color) => ({
    background: color || '#00d4ff',
    color: color ? 'white' : 'black',
    border: 'none',
    padding: '6px 12px',
    borderRadius: '4px',
    cursor: 'pointer',
    marginRight: '5px',
    fontWeight: 'bold',
  }),
  input: {
    background: '#0f3460',
    border: '1px solid #00d4ff',
    color: 'white',
    padding: '8px 12px',
    borderRadius: '5px',
    width: '100%',
    marginBottom: '10px',
  },
  sectionTitle: {
    color: '#00d4ff',
    fontSize: '20px',
    marginBottom: '15px',
  },
  refreshBtn: {
    background: '#0f3460',
    color: '#00d4ff',
    border: '1px solid #00d4ff',
    padding: '8px 15px',
    borderRadius: '5px',
    cursor: 'pointer',
    float: 'right',
  },
  logEntry: {
    fontFamily: 'monospace',
    fontSize: '12px',
    padding: '5px 0',
    borderBottom: '1px solid #0f3460',
    color: '#aaa',
  },
  workloadStatus: (status) => ({
    background: status === 'running' ? '#00b300' :
                status === 'failed' ? '#cc0000' : '#888',
    padding: '3px 8px',
    borderRadius: '3px',
    fontSize: '12px',
    fontWeight: 'bold',
  }),
};

// Dashboard Tab
function Dashboard({ nodes, vipHolder, logs }) {
  return (
    <div>
      <div style={styles.nodeGrid}>
        {Object.entries(nodes).map(([id, info]) => (
          <div key={id} style={styles.nodeCard(info.alive ? 'alive' : 'down')}>
            <h2>{id.toUpperCase()}</h2>
            <p style={{ color: '#888' }}>{info.role}</p>
            <div style={styles.statusBadge(info.alive ? 'alive' : 'down')}>
              {info.alive ? 'ONLINE' : 'OFFLINE'}
            </div>
            {info.alive && (
              <p style={{ color: '#888', fontSize: '12px' }}>
                Load: {info.load} / {info.capacity}
              </p>
            )}
            {id === vipHolder && (
              <div style={styles.vipBadge}>⭐ HOLDS VIRTUAL IP</div>
            )}
          </div>
        ))}
      </div>

      <div style={styles.card}>
        <h3 style={styles.sectionTitle}>📋 Recent Logs</h3>
        {logs.length === 0 ? (
          <p style={{ color: '#888' }}>No logs yet</p>
        ) : (
          logs.map((log, i) => (
            <div key={i} style={styles.logEntry}>{log}</div>
          ))
        )}
      </div>
    </div>
  );
}

// Workloads Tab
function Workloads({ workloads, onDeploy, onStop, onRemove,onRestart }) {
  const [name, setName] = useState('');
  const [image, setImage] = useState('');
  const [port, setPort] = useState('');
  const [hostPort, setHostPort] = useState('');
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState('');

  const handleDeploy = async () => {
    if (!name || !image) {
      setError('Name and image are required');
      return;
    }
    setDeploying(true);
    setError('');
    const spec = { image };
    if (port && hostPort) {
      spec.ports = { [`${port}/tcp`]: parseInt(hostPort) };
    }
    await onDeploy(name, spec);
    setName('');
    setImage('');
    setPort('');
    setHostPort('');
    setDeploying(false);
  };

  return (
    <div>
      <div style={styles.card}>
        <h3 style={styles.sectionTitle}>🚀 Deploy New Workload</h3>
        {error && (
          <p style={{ color: '#cc0000', marginBottom: '10px' }}>{error}</p>
        )}
        <input
          style={styles.input}
          placeholder="Workload name (e.g. my-app)"
          value={name}
          onChange={e => setName(e.target.value)}
        />
        <input
          style={styles.input}
          placeholder="Docker image (e.g. nginx:alpine)"
          value={image}
          onChange={e => setImage(e.target.value)}
        />
        <div style={{ display: 'flex', gap: '10px' }}>
          <input
            style={{ ...styles.input, width: '50%' }}
            placeholder="Container port (e.g. 80)"
            value={port}
            onChange={e => setPort(e.target.value)}
          />
          <input
            style={{ ...styles.input, width: '50%' }}
            placeholder="Host port (e.g. 8080)"
            value={hostPort}
            onChange={e => setHostPort(e.target.value)}
          />
        </div>
        <button
          style={styles.btn()}
          onClick={handleDeploy}
          disabled={deploying}
        >
          {deploying ? 'Deploying...' : '🚀 Deploy'}
        </button>
      </div>

      <div style={styles.card}>
        <h3 style={styles.sectionTitle}>📦 Running Workloads</h3>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Image</th>
              <th style={styles.th}>Node</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {workloads.length === 0 ? (
              <tr>
                <td colSpan={5} style={{
                  ...styles.td,
                  textAlign: 'center',
                  color: '#888'
                }}>
                  No workloads deployed
                </td>
              </tr>
            ) : (
              workloads.map((w, i) => (
                <tr key={i}>
                  <td style={styles.td}>{w.name}</td>
                  <td style={styles.td}>{w.spec?.image}</td>
                  <td style={styles.td}>{w.node_id || 'N/A'}</td>
                  <td style={styles.td}>
                    <span style={styles.workloadStatus(w.status)}>
                      {w.status?.toUpperCase()}
                    </span>
                  </td>
                  <td style={styles.td}>
  {w.status === 'running' && (
    <button
      style={styles.btn('#ff6600')}
      onClick={() => onStop(w.name)}
    >
      Stop
    </button>
  )}
  {w.status === 'stopped' && (
    <button
      style={styles.btn('#00b300')}
      onClick={() => onRestart(w.name)}
    >
      Restart
    </button>
  )}
  <button
    style={styles.btn('#cc0000')}
    onClick={() => onRemove(w.name)}
  >
    Remove
  </button>
</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Main App
function App() {
  const [tab, setTab] = useState('dashboard');
  const [nodes, setNodes] = useState({});
  const [workloads, setWorkloads] = useState([]);
  const [logs, setLogs] = useState([]);
  const [vipHolder, setVipHolder] = useState('unknown');
  const [lastUpdated, setLastUpdated] = useState('');

  const fetchData = async () => {
    try {
      const nodesRes = await axios.get(`${SCHEDULER_URL}/nodes/status`);
      setNodes(nodesRes.data);

      const workloadsRes = await axios.get(
        `${MANAGER_URL}/manager/workloads`
      );
      setWorkloads(workloadsRes.data);

      const runningOnMaster = workloadsRes.data.some(
        w => w.node_id === 'master-1' && w.status === 'running'
      );
      setVipHolder(runningOnMaster ? 'master-1' : 'slave-1');
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      console.error('Failed to fetch data:', err);
    }
  };

const fetchLogs = async () => {
    try {
      const res = await axios.get(
        `${MANAGER_URL}/manager/logs`
      );
      setLogs(res.data);
    } catch {
      setLogs(['Logs not available']);
    }
  };

  useEffect(() => {
    fetchData();
    fetchLogs();
    const interval = setInterval(() => {
      fetchData();
      fetchLogs();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDeploy = async (name, spec) => {
    try {
      await axios.post(`${MANAGER_URL}/manager/deploy`, { name, spec });
      await fetchData();
    } catch (err) {
      alert('Deploy failed: ' + (err.response?.data?.error || err.message));
    }
  };

  const handleStop = async (name) => {
    try {
      await axios.post(`${MANAGER_URL}/manager/workloads/${name}/stop`);
      await fetchData();
    } catch (err) {
      alert('Stop failed: ' + (err.response?.data?.error || err.message));
    }
  };

  const handleRemove = async (name) => {
    if (!window.confirm(`Remove workload "${name}"?`)) return;
    try {
      await axios.delete(`${MANAGER_URL}/manager/workloads/${name}`);
      await fetchData();
    } catch (err) {
      alert('Remove failed: ' + (err.response?.data?.error || err.message));
    }
  };

const handleRestart = async (name) => {
  try {
    await axios.post(
      `${MANAGER_URL}/manager/workloads/${name}/start`
    );
    await fetchData();
  } catch (err) {
    alert('Restart failed: ' + 
      (err.response?.data?.error || err.message));
  }
};

  return (
    <div style={styles.app}>
      <h1 style={styles.header}>
        🖥️ High Availability Cluster Dashboard
      </h1>
      <p style={styles.subtitle}>
        Auto-refreshes every 5 seconds | Last updated: {lastUpdated}
      </p>

      <div style={styles.nav}>
        {['dashboard', 'workloads'].map(t => (
          <button
            key={t}
            style={styles.navBtn(tab === t)}
            onClick={() => setTab(t)}
          >
            {t === 'dashboard' ? '📊 Dashboard' : '📦 Workloads'}
          </button>
        ))}
        <button style={styles.refreshBtn} onClick={fetchData}>
          🔄 Refresh
        </button>
      </div>

      {tab === 'dashboard' && (
        <Dashboard
          nodes={nodes}
          vipHolder={vipHolder}
          logs={logs}
        />
      )}
      {tab === 'workloads' && (
        <Workloads
          workloads={workloads}
          onDeploy={handleDeploy}
          onStop={handleStop}
          onRemove={handleRemove}
	  onRestart={handleRestart}
        />
      )}
    </div>
  );
}

export default App;
