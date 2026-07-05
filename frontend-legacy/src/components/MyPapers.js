const E5O_STAGES = [
  ['TOPIC_INIT', 'Understanding your idea', 'Scoping'],
  ['PROBLEM_DECOMPOSE', 'Breaking it into research questions', 'Scoping'],
  ['SEARCH_STRATEGY', 'Planning the literature search', 'Literature'],
  ['LITERATURE_COLLECT', 'Collecting papers', 'Literature'],
  ['LITERATURE_SCREEN', 'Screening for relevance', 'Literature'],
  ['KNOWLEDGE_EXTRACT', 'Extracting key findings', 'Literature'],
  ['SYNTHESIS', "Synthesizing what's known", 'Hypothesis'],
  ['HYPOTHESIS_GEN', 'Forming the hypothesis', 'Hypothesis'],
  ['EXPERIMENT_DESIGN', 'Designing the experiments', 'Experiments'],
  ['CODE_GENERATION', 'Writing the experiment code', 'Experiments'],
  ['RESOURCE_PLANNING', 'Planning compute resources', 'Experiments'],
  ['EXPERIMENT_RUN', 'Running the experiments', 'Experiments'],
  ['ITERATIVE_REFINE', 'Refining the experiments', 'Experiments'],
  ['RESULT_ANALYSIS', 'Analyzing the results', 'Analysis'],
  ['RESEARCH_DECISION', 'Deciding how to proceed', 'Analysis'],
  ['PAPER_OUTLINE', 'Outlining the paper', 'Writing'],
  ['PAPER_DRAFT', 'Writing the draft', 'Writing'],
  ['PEER_REVIEW', 'Running peer review', 'Writing'],
  ['PAPER_REVISION', 'Revising the paper', 'Writing'],
  ['QUALITY_GATE', 'Final quality checks', 'Finalizing'],
  ['KNOWLEDGE_ARCHIVE', 'Archiving what was learned', 'Finalizing'],
  ['EXPORT_PUBLISH', 'Exporting the deliverables', 'Finalizing'],
  ['CITATION_VERIFY', 'Verifying every citation', 'Finalizing'],
];

/**
 * MyPapers — the paper library and per-paper page (live progress, narration,
 * chat, and the finished document). The paper page is the product's anchor.
 */
const MyPapers = {
  _detail: null,
  _pendingId: null,
  _pollTimer: null,

  async render(container) {
    this._container = container;
    this._stopPolling();

    if (this._pendingId) {
      const id = this._pendingId;
      this._pendingId = null;
      return this._open(id);
    }
    this._detail = null;  // navigating to the list always leaves the detail view

    container.innerHTML = `
      <div class="card" style="max-width:780px;margin:0 auto">
        <h2 style="margin-bottom:4px">📚 My Papers</h2>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:18px">
          Everything you've started, safe and permanent.</p>
        <div id="papers-list"><div style="color:var(--text-muted);padding:20px 0">Loading your papers…</div></div>
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

  _statusPill(status) {
    const label = { running: 'Writing…', completed: 'Ready', failed: 'Failed' }[status] || status;
    return `<span class="g-pill ${status}">${label}</span>`;
  },

  _renderList(papers) {
    const el = document.getElementById('papers-list');
    if (!el) return;
    if (!papers.length) {
      el.innerHTML = `
        <div style="text-align:center;padding:36px 0">
          <div style="font-size:40px;margin-bottom:10px">📝</div>
          <p style="color:var(--text-secondary);margin-bottom:16px">No papers yet.</p>
          <a href="#newpaper" class="g-btn primary" style="text-decoration:none">Start your first paper</a>
        </div>`;
      return;
    }
    el.innerHTML = papers.map(p => `
      <a href="#papers/${p.id}" style="text-decoration:none;color:inherit">
      <div style="padding:16px;border:1px solid var(--glass-border);border-radius:12px;margin-bottom:10px;cursor:pointer;background:var(--glass-highlight)">
        <div style="display:flex;align-items:center;gap:12px">
          <span style="font-weight:600;flex:1;font-size:15px">${p.title || p.topic || 'Untitled paper'}</span>
          ${this._statusPill(p.status)}
        </div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:6px">
          Started ${(p.created_at || '').replace('T', ' ').slice(0, 16)}
        </div>
      </div></a>
    `).join('');
  },

  async _open(id) {
    try {
      this._detail = await API.get(`/papers/${id}`);
      if (location.hash !== `#papers/${id}`) history.replaceState(null, '', `#papers/${id}`);
      this._renderDetail();
      if (this._detail.status === 'running') this._startPolling();
    } catch (e) {
      Toast.error(`Couldn't open that paper: ${e.message}`);
    }
  },

  back() {
    this._detail = null;
    this._stopPolling();
    location.hash = 'mypapers';
    this.render(this._container);
  },

  /* ---------- live progress ---------- */

  _startPolling() {
    this._stopPolling();
    this._pollTimer = setInterval(() => this._refreshLive(), 8000);
    this._refreshLive();
  },

  _stopPolling() {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
  },

  async _refreshLive() {
    if (!this._detail || this._detail.status !== 'running') return this._stopPolling();
    try {
      const status = await API.pipelineStatus();
      if (status.run_id === this._detail.run_id) {
        this._live = status.progress || null;
        if (['completed', 'failed'].includes(status.status)) {
          this._detail = await API.get(`/papers/${this._detail.id}`);
          this._stopPolling();
          Toast[this._detail.status === 'completed' ? 'success' : 'error'](
            this._detail.status === 'completed' ? 'Your paper is ready! 🎉' : 'The run hit a problem.');
          return this._renderDetail();
        }
      } else if (status.status === 'idle' || status.run_id !== this._detail.run_id) {
        this._detail = await API.get(`/papers/${this._detail.id}`);
        if (this._detail.status !== 'running') { this._stopPolling(); return this._renderDetail(); }
      }
      this._renderStageRail();
    } catch (e) { /* transient — keep polling */ }
  },

  onEvent(event) {
    if (event.type === 'stage_complete' && this._detail && this._detail.status === 'running') {
      this._refreshLive();
    }
  },

  /* ---------- the paper page ---------- */

  _renderDetail() {
    const p = this._detail;
    const running = p.status === 'running';
    this._container.innerHTML = `
      <div style="max-width:880px;margin:0 auto">
        <a href="#mypapers" class="g-btn subtle" style="text-decoration:none;display:inline-block;margin-bottom:14px">← All papers</a>

        <div class="card" style="margin-bottom:16px">
          <div style="display:flex;align-items:flex-start;gap:12px">
            <div style="flex:1">
              <h2 style="font-size:20px;line-height:1.3">${p.title || p.topic || 'Untitled paper'}</h2>
              <p style="font-size:13px;color:var(--text-muted);margin-top:6px">${p.topic || ''}</p>
              ${p.plan && p.plan.hypothesis ? `<p style="font-size:13px;color:var(--text-secondary);margin-top:8px;font-style:italic">Hypothesis under test: ${p.plan.hypothesis}</p>` : ''}
            </div>
            ${this._statusPill(p.status)}
          </div>
          ${p.status === 'failed' ? `
            <div style="margin-top:14px;padding:12px;border:1px solid var(--error);border-radius:10px;font-size:13px">
              Something went wrong: ${p.error || 'unknown error'}.
              <button id="paper-retry" class="g-btn subtle" style="margin-left:10px">↻ Try again</button>
            </div>` : ''}
          ${p.status === 'completed' ? `
            <div style="display:flex;gap:8px;margin-top:16px">
              ${p.paper_md ? '<button class="g-btn primary dl-btn" data-kind="md">⬇ Download (Markdown)</button>' : ''}
              ${p.paper_tex ? '<button class="g-btn dl-btn" data-kind="tex">⬇ Download (LaTeX)</button>' : ''}
            </div>` : ''}
        </div>

        <div class="card" style="margin-bottom:16px">
          <h3 style="font-size:15px;margin-bottom:4px">${running ? 'Writing your paper…' : 'How this paper was made'}</h3>
          <p style="font-size:12.5px;color:var(--text-muted)" id="stage-headline"></p>
          <div id="stage-rail" style="margin-top:12px"></div>
        </div>

        <div class="card" style="margin-bottom:16px">
          <h3 style="font-size:15px;margin-bottom:10px">💬 Talk to your researcher</h3>
          <div class="chat-dock">
            <div class="chat-msgs" id="paper-chat-msgs">
              <div class="chat-msg ai">${running
                ? "I'm working on your paper right now. Ask me what's happening, or give me direction — “focus on recent studies”, “keep the tone formal” — and I'll apply it as I go."
                : "Ask me anything about this paper — how it was made, why I made the choices I did."}</div>
            </div>
            <div style="display:flex;gap:8px;padding:10px;border-top:1px solid var(--glass-border)">
              <input id="paper-chat-input" class="g-input" placeholder="Ask a question or give direction…" style="flex:1" />
              <button id="paper-chat-send" class="g-btn primary">Send</button>
            </div>
          </div>
        </div>

        ${p.status === 'completed' && (p.paper_md || p.paper_tex) ? `
        <div class="card">
          <h3 style="font-size:15px;margin-bottom:12px">📄 The paper</h3>
          <div id="paper-body" style="font-size:14.5px;line-height:1.7;max-height:70vh;overflow-y:auto"></div>
        </div>` : ''}
      </div>
    `;

    // Bind
    this._container.querySelectorAll('.dl-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset.kind;
        const base = (p.title || 'paper').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
        this._download(`${base}.${kind}`, kind === 'md' ? p.paper_md : p.paper_tex);
      });
    });
    const retry = document.getElementById('paper-retry');
    if (retry) retry.addEventListener('click', () => this._retry());
    const send = document.getElementById('paper-chat-send');
    const input = document.getElementById('paper-chat-input');
    if (send && input) {
      const go = () => this._chat(input);
      send.addEventListener('click', go);
      input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
    }

    const body = document.getElementById('paper-body');
    if (body) body.innerHTML = this._renderMarkdown(p.paper_md || p.paper_tex || '');
    this._renderStageRail();
  },

  _renderStageRail() {
    const rail = document.getElementById('stage-rail');
    const headline = document.getElementById('stage-headline');
    if (!rail || !this._detail) return;
    const p = this._detail;
    const running = p.status === 'running';
    const snap = running ? this._live : null;
    const dbLog = p.stage_log || [];

    const summaries = {};
    dbLog.forEach(e => { summaries[e.key] = e.summary; });
    if (snap) (snap.log || []).forEach(e => { summaries[e.key] = e.summary; });

    // Build the full 23-stage map: live snapshot when running, history otherwise
    let stages;
    if (snap && (snap.stages || []).length) {
      stages = snap.stages;
    } else {
      const doneKeys = new Set(dbLog.map(e => e.key));
      stages = E5O_STAGES.map(([key, label, phase]) => ({
        key, label, phase,
        state: p.status === 'completed' ? 'done' : (doneKeys.has(key) ? 'done' : 'pending'),
      }));
      if (running && !dbLog.length) {
        stages[0].state = 'active';
      }
    }

    if (headline) {
      if (snap && snap.current) {
        const cur = stages.find(s => s.key === snap.current);
        headline.textContent = cur ? `Now: ${cur.label}` : '';
      } else if (running) {
        headline.textContent = 'Connecting to the live run…';
      } else {
        headline.textContent = '';
      }
    }

    let html = '', phase = '';
    stages.forEach((s, i) => {
      if (s.phase !== phase) { phase = s.phase; html += `<div class="stage-phase">${phase}</div>`; }
      html += `
        <div class="stage-item ${s.state}">
          <div class="dot">${s.state === 'done' ? '✓' : ''}</div>
          <div style="flex:1">
            <div class="stage-label">${i + 1}. ${s.label}</div>
            ${summaries[s.key] ? `<div class="stage-summary">${summaries[s.key]}</div>` : ''}
          </div>
        </div>`;
    });
    rail.innerHTML = html;
  },

  async _chat(input) {
    const msg = input.value.trim();
    if (!msg) return;
    const box = document.getElementById('paper-chat-msgs');
    box.insertAdjacentHTML('beforeend', `<div class="chat-msg me">${msg.replace(/</g, '&lt;')}</div>`);
    input.value = '';
    box.insertAdjacentHTML('beforeend', `<div class="chat-msg ai" id="chat-pending">…</div>`);
    box.scrollTop = box.scrollHeight;
    try {
      const res = await API.post('/paper/chat', { message: msg, run_id: this._detail.run_id });
      document.getElementById('chat-pending').outerHTML =
        `<div class="chat-msg ai">${(res.ok ? res.reply : `Sorry — ${res.error}`).replace(/</g, '&lt;')}</div>`;
    } catch (e) {
      document.getElementById('chat-pending').outerHTML =
        `<div class="chat-msg ai">Sorry — ${e.message}</div>`;
    }
    box.scrollTop = box.scrollHeight;
  },

  async _retry() {
    try {
      const p = this._detail;
      const res = await API.post('/pipeline/start', {
        topic: p.topic, title: p.title, plan: p.plan, auto_approve: true,
      });
      Toast.success('Restarted — writing your paper again.');
      const row = await API.get(`/papers/by-run/${res.run_id}`);
      this._open(row.id);
    } catch (e) {
      Toast.error(String(e.message).includes('409')
        ? 'Another paper is currently being written — wait for it to finish first.'
        : `Couldn't restart: ${e.message}`);
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

  // Minimal markdown renderer (headers, bold, italics, lists, paragraphs, code)
  _renderMarkdown(src) {
    const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const lines = esc(src).split('\n');
    let html = '', inList = false, inCode = false;
    for (const line of lines) {
      if (line.trim().startsWith('```')) {
        html += inCode ? '</pre>' : '<pre style="background:var(--bg-tertiary);padding:12px;border-radius:8px;overflow-x:auto;font-size:12.5px">';
        inCode = !inCode; continue;
      }
      if (inCode) { html += line + '\n'; continue; }
      const fmt = t => t
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code style="background:var(--bg-tertiary);padding:1px 5px;border-radius:4px;font-size:.9em">$1</code>');
      const h = line.match(/^(#{1,4})\s+(.*)/);
      if (h) {
        if (inList) { html += '</ul>'; inList = false; }
        const level = h[1].length;
        html += `<h${level + 1} style="margin:18px 0 8px;font-size:${20 - level * 2}px">${fmt(h[2])}</h${level + 1}>`;
        continue;
      }
      if (/^\s*[-*]\s+/.test(line)) {
        if (!inList) { html += '<ul style="margin:8px 0 8px 22px">'; inList = true; }
        html += `<li style="margin-bottom:4px">${fmt(line.replace(/^\s*[-*]\s+/, ''))}</li>`;
        continue;
      }
      if (inList) { html += '</ul>'; inList = false; }
      if (line.trim() === '') continue;
      html += `<p style="margin:8px 0">${fmt(line)}</p>`;
    }
    if (inList) html += '</ul>';
    if (inCode) html += '</pre>';
    return html;
  },
};
