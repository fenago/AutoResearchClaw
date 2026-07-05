/**
 * REST API client for ResearchClaw.
 */
const API = {
  base: '/api',

  _authHeaders() {
    const token = (typeof Auth !== 'undefined' && Auth.token && Auth.token()) || null;
    return token ? { Authorization: `Bearer ${token}` } : {};
  },

  _checkAuth(res) {
    if (res.status === 401 && typeof Auth !== 'undefined' && Auth.cfg && Auth.cfg.enabled) {
      Auth.handleUnauthorized();
    }
  },

  async get(path) {
    const res = await fetch(`${this.base}${path}`, { headers: this._authHeaders() });
    this._checkAuth(res);
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },

  async post(path, body = {}) {
    const res = await fetch(`${this.base}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...this._authHeaders() },
      body: JSON.stringify(body),
    });
    this._checkAuth(res);
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },

  // Convenience methods
  health() { return this.get('/health'); },
  config() { return this.get('/config'); },
  pipelineStatus() { return this.get('/pipeline/status'); },
  pipelineStages() { return this.get('/pipeline/stages'); },
  startPipeline(opts) { return this.post('/pipeline/start', opts); },
  stopPipeline() { return this.post('/pipeline/stop'); },
  listRuns() { return this.get('/runs'); },
  getRun(id) { return this.get(`/runs/${id}`); },
  getMetrics(id) { return this.get(`/runs/${id}/metrics`); },
  listProjects() { return this.get('/projects'); },
};
