/**
 * MyPapers — your saved papers, kept safe in the database (not the container).
 */
const MyPapers = {
  _detail: null,

  async render(container) {
    this._container = container;
    if (this._detail) return this._renderDetail();
    container.innerHTML = `
      <div class="card" style="max-width:760px;margin:0 auto">
        <h2>📚 My Papers</h2>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">
          Every paper you start is saved here — running, finished, or failed.</p>
        <div id="papers-list">Loading…</div>
      </div>
    `;
    try {
      const res = await API.get('/papers');
      this._renderList(res.papers || []);
    } catch (e) {
      const el = document.getElementById('papers-list');
      if (el) el.innerHTML = `<p style="color:var(--error)">Couldn't load your papers: ${e.message}</p>`;
    }
  },

  _badge(status) {
    const cls = { running: 'running', completed: 'running', failed: 'failed' }[status] || 'idle';
    const color = status === 'completed' ? 'var(--success)' : status === 'failed' ? 'var(--error)' : 'var(--accent)';
    return `<span class="status-badge ${cls}" style="color:${color}">${status}</span>`;
  },

  _renderList(papers) {
    const el = document.getElementById('papers-list');
    if (!el) return;
    if (!papers.length) {
      el.innerHTML = `<p style="color:var(--text-muted)">No papers yet — go to ✍️ New Paper and tell me your first idea.</p>`;
      return;
    }
    el.innerHTML = papers.map(p => `
      <div class="paper-row" data-id="${p.id}"
        style="padding:14px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:8px;cursor:pointer">
        <div style="display:flex;align-items:center;gap:10px">
          <span style="font-weight:600;flex:1">${p.title || p.topic || p.run_id}</span>
          ${this._badge(p.status)}
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px">
          Started ${(p.created_at || '').replace('T', ' ').slice(0, 16)}
          ${p.error ? ` — <span style="color:var(--error)">${p.error.slice(0, 120)}</span>` : ''}
        </div>
      </div>
    `).join('');
    el.querySelectorAll('.paper-row').forEach(row => {
      row.addEventListener('click', () => this._open(row.dataset.id));
    });
  },

  async _open(id) {
    try {
      this._detail = await API.get(`/papers/${id}`);
      this._renderDetail();
    } catch (e) {
      alert(`Couldn't open paper: ${e.message}`);
    }
  },

  _download(name, content) {
    const blob = new Blob([content], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  },

  _renderDetail() {
    const p = this._detail;
    const body = p.paper_md || p.paper_tex || '';
    const extras = Object.keys(p.artifacts || {});
    this._container.innerHTML = `
      <div class="card" style="max-width:860px;margin:0 auto">
        <button id="papers-back" style="padding:6px 14px;margin-bottom:14px;border:1px solid var(--border);border-radius:6px;background:var(--bg-tertiary);color:var(--text-primary);cursor:pointer">← All papers</button>
        <div style="display:flex;align-items:center;gap:10px">
          <h2 style="flex:1">${p.title || p.topic || p.run_id}</h2>
          ${this._badge(p.status)}
        </div>
        <p style="font-size:13px;color:var(--text-muted);margin:6px 0 14px">${p.topic || ''}</p>

        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
          ${p.paper_md ? `<button class="dl-btn" data-kind="md" style="padding:7px 14px;border:none;border-radius:6px;background:var(--accent);color:#fff;cursor:pointer">⬇ Download (Markdown)</button>` : ''}
          ${p.paper_tex ? `<button class="dl-btn" data-kind="tex" style="padding:7px 14px;border:1px solid var(--border);border-radius:6px;background:var(--bg-tertiary);color:var(--text-primary);cursor:pointer">⬇ Download (LaTeX)</button>` : ''}
        </div>

        ${p.status === 'running' ? `<p style="color:var(--accent);font-size:14px">⏳ Still being written — watch progress on the 🔬 Progress page.</p>` : ''}
        ${body ? `<pre style="white-space:pre-wrap;font-family:var(--font-sans);font-size:14px;line-height:1.6;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:var(--radius);padding:18px;max-height:60vh;overflow-y:auto">${body.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>` : ''}
        ${!body && p.status !== 'running' ? `<p style="color:var(--text-muted)">No document was saved for this run.</p>` : ''}
        ${extras.length ? `<p style="font-size:12px;color:var(--text-muted);margin-top:10px">Also saved: ${extras.join(', ')}</p>` : ''}
      </div>
    `;
    document.getElementById('papers-back').addEventListener('click', () => { this._detail = null; this.render(this._container); });
    this._container.querySelectorAll('.dl-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset.kind;
        const base = (p.title || 'paper').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
        this._download(`${base}.${kind}`, kind === 'md' ? p.paper_md : p.paper_tex);
      });
    });
  },
};
