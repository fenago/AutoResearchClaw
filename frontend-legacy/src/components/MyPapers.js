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
    const label = { running: 'Writing…', queued: 'Queued', completed: 'Ready', failed: 'Failed', paused: 'Paused', stopped: 'Stopped' }[status] || status;
    const cls = { paused: 'running', stopped: 'failed' }[status] || status;
    return `<span class="g-pill ${cls}">${label}</span>`;
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
      if (['running', 'queued'].includes(this._detail.status)) this._startPolling();
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
    this._pollTimer = setInterval(() => this._refreshLive(), 5000);
    this._refreshLive();
  },

  _stopPolling() {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
    this._stopTicker();
  },

  async _refreshLive() {
    if (!this._detail || !['running', 'queued'].includes(this._detail.status)) return this._stopPolling();
    try {
      if (this._detail.status === 'queued') {
        const fresh = await API.get(`/papers/${this._detail.id}`);
        if (fresh.status !== 'queued') { this._detail = fresh; this._renderDetail(); if (fresh.status !== 'running') this._stopPolling(); }
        return;
      }
      const status = await API.pipelineStatus();
      if (status.run_id === this._detail.run_id) {
        this._live = status.progress || null;
        this._status_waiting = status.waiting || null;
        if (['completed', 'failed', 'paused', 'stopped'].includes(status.status)) {
          this._detail = await API.get(`/papers/${this._detail.id}`);
          this._stopPolling();
          const st = this._detail.status;
          if (st === 'completed') Toast.success('Your paper is ready! 🎉');
          else if (st === 'paused') Toast.info('Paused — resume whenever you like.');
          else if (st !== 'stopped') Toast.error('The run hit a problem.');
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
          ${p.plan && p.plan.copilot ? `<p style="font-size:12px;color:var(--accent);margin-top:8px">🎛️ Co-pilot mode — I'll pause at the key decisions for your call.</p>` : ''}
          ${p.status === 'queued' ? `
            <p style="margin-top:14px;font-size:13px;color:var(--text-secondary)">⏳ In line — another paper is being written right now. Yours starts automatically when it finishes.</p>` : ''}
          ${(p.status === 'failed' || p.status === 'stopped') ? `
            <div style="margin-top:14px;padding:12px;border:1px solid ${p.status === 'stopped' ? 'var(--glass-border)' : 'var(--error)'};border-radius:10px;font-size:13px">
              ${p.status === 'stopped' ? 'This run was stopped.' : ('Something went wrong: ' + (p.error || 'unknown error') + '.')}
              <button id="paper-retry" class="g-btn subtle" style="margin-left:10px">↻ Start over</button>
            </div>` : ''}
          <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
            ${running ? '<button id="paper-pause" class="g-btn subtle">⏸ Pause after this stage</button>' : ''}
            ${p.status === 'paused' ? '<button id="paper-resume" class="g-btn primary">▶ Resume</button>' : ''}
            ${p.status === 'completed' && p.paper_md ? '<button class="g-btn primary dl-btn" data-kind="md">⬇ Download (Markdown)</button>' : ''}
            ${p.status === 'completed' && p.paper_tex ? '<button class="g-btn dl-btn" data-kind="tex">⬇ Download (LaTeX)</button>' : ''}
          </div>
        </div>

        <div id="gate-card"></div>

        <div class="card" style="margin-bottom:16px">
          <div style="display:flex;align-items:baseline;gap:10px">
            <h3 style="font-size:15px;flex:1">${running ? 'Writing your paper' : (p.status === 'queued' ? 'The plan — 23 stages, starting soon' : 'How this paper was made')}</h3>
            <span id="progress-count" style="font-size:12px;color:var(--text-muted)"></span>
          </div>
          ${running ? `
          <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
          <div id="active-work" style="margin-top:14px"></div>` : ''}
          <div id="stage-rail" style="margin-top:14px"></div>
        </div>

        <div class="card" style="margin-bottom:16px">
          <h3 style="font-size:15px;margin-bottom:10px">💬 Your research assistant</h3>
          <div class="chat-dock">
            <div class="chat-msgs" id="paper-chat-msgs">
              <div class="chat-msg ai">${running
                ? "This is your research — I'm the assistant doing the legwork. Direct me anytime: “focus on recent studies”, “drop that benchmark”, “keep the tone formal”. Or ask what I'm finding."
                : "Ask me anything about your paper — what I found, why the research went the way it did."}</div>
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
    const pauseBtn = document.getElementById('paper-pause');
    if (pauseBtn) pauseBtn.addEventListener('click', () => this._pause());
    const resumeBtn = document.getElementById('paper-resume');
    if (resumeBtn) resumeBtn.addEventListener('click', () => this._resume());
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

    // Progress bar + live "what I'm doing right now" card
    const fill = document.getElementById('progress-fill');
    const count = document.getElementById('progress-count');
    const work = document.getElementById('active-work');
    if (snap && fill) {
      fill.style.width = `${Math.max(2, snap.percent || 0)}%`;
      if (count) count.textContent = `Stage ${Math.min((snap.done || 0) + 1, snap.total || 23)} of ${snap.total || 23} · ${snap.percent || 0}% complete`;
      const cur = stages.find(x => x.key === snap.current);
      if (work && cur) {
        this._stageStarted = snap.stage_started ? snap.stage_started * 1000 : this._stageStarted;
        work.innerHTML = `
          <div style="display:flex;gap:12px;align-items:flex-start;padding:14px;border:1px solid var(--glass-border);border-radius:12px;background:linear-gradient(90deg, rgba(88,166,255,0.07), transparent)">
            <div class="dot-throb"></div>
            <div style="flex:1">
              <div style="font-size:14px;font-weight:600;color:var(--accent)">${cur.label}<span class="ellipsis"></span></div>
              <div style="font-size:12.5px;color:var(--text-secondary);margin-top:3px">${snap.doing || ''}</div>
              <div style="font-size:11.5px;color:var(--text-muted);margin-top:6px">
                <span id="stage-elapsed"></span>
              </div>
              ${(snap.activity || []).length ? `
              <div style="margin-top:8px;display:flex;flex-direction:column;gap:2px">
                ${snap.activity.slice(0, 4).map(a => `
                  <div style="font-size:11.5px;color:var(--text-muted);font-family:var(--font-mono)">
                    ↳ ${a.file} <span style="opacity:.7">· ${a.ago < 60 ? a.ago + 's' : Math.floor(a.ago / 60) + 'm'} ago</span>
                  </div>`).join('')}
              </div>` : ''}
            </div>
          </div>`;
        this._startTicker();
      } else if (work) {
        work.innerHTML = `<div style="font-size:13px;color:var(--text-muted)">Connecting to the live run…</div>`;
      }
    } else if (running && work) {
      work.innerHTML = `<div style="font-size:13px;color:var(--text-muted)">Connecting to the live run…</div>`;
    }

    const canRedo = ['completed', 'failed', 'stopped', 'paused'].includes(p.status);
    let html = '', phase = '';
    stages.forEach((s, i) => {
      if (s.phase !== phase) { phase = s.phase; html += `<div class="stage-phase">${phase}</div>`; }
      html += `
        <div class="stage-item ${s.state}" data-stage="${i + 1}" style="cursor:pointer" title="Click to see what happened here">
          <div class="dot">${s.state === 'done' ? '✓' : ''}</div>
          <div style="flex:1">
            <div class="stage-label">${i + 1}. ${s.label} <span style="opacity:.5;font-size:11px">›</span></div>
            ${summaries[s.key] ? `<div class="stage-summary">${summaries[s.key]}</div>` : ''}
          </div>
          ${canRedo && s.state === 'done' ? `<button class="stage-redo" data-redo="${i + 1}" title="Redo from this step" style="background:none;border:1px solid var(--glass-border);border-radius:6px;color:var(--text-muted);cursor:pointer;font-size:11px;padding:2px 7px;align-self:center">↻</button>` : ''}
        </div>`;
    });
    rail.innerHTML = html;

    // Click a stage → open the transparency drawer (what/reasoning/files)
    rail.querySelectorAll('.stage-item').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.stage-redo')) return;
        if (typeof StageDrawer !== 'undefined') StageDrawer.open(p.id, parseInt(el.dataset.stage, 10));
      });
    });
    rail.querySelectorAll('.stage-redo').forEach(btn => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); this._redo(parseInt(btn.dataset.redo, 10)); });
    });

    // Co-pilot decision card when the run is waiting at a gate
    this._renderGateCard();
  },

  _renderGateCard() {
    const host = document.getElementById('gate-card');
    if (!host) return;
    const w = (this._live && this._status_waiting) ? this._status_waiting : null;
    if (!w) { host.innerHTML = ''; return; }
    host.innerHTML = `
      <div class="card" style="margin-bottom:16px;border:1px solid var(--accent)">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="font-size:16px">🎛️</span>
          <h3 style="font-size:15px">Your call: ${w.stage_name || 'a key decision'}</h3>
        </div>
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:8px">
          I've paused so you can review this step before I go on. ${w.context_summary || ''}
          Click the stage above to see exactly what I produced.</p>
        <textarea id="gate-guidance" class="g-textarea" rows="2" placeholder="Optional: tell me what to change or emphasize…" style="margin-bottom:10px"></textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button id="gate-approve" class="g-btn success">✓ Looks right — continue</button>
          <button id="gate-adjust" class="g-btn primary">✎ Continue with my notes</button>
          <button id="gate-reject" class="g-btn danger">✗ Stop — this isn't right</button>
        </div>
      </div>`;
    const g = () => (document.getElementById('gate-guidance') || {}).value || '';
    document.getElementById('gate-approve').addEventListener('click', () => this._gate('approve', ''));
    document.getElementById('gate-adjust').addEventListener('click', () => this._gate('adjust', g()));
    document.getElementById('gate-reject').addEventListener('click', () => this._gate('reject', g()));
  },

  _startTicker() {
    if (this._tickTimer) return;
    this._tickTimer = setInterval(() => {
      const el = document.getElementById('stage-elapsed');
      if (!el || !this._stageStarted) return;
      const secs = Math.max(0, Math.floor((Date.now() - this._stageStarted) / 1000));
      const m = Math.floor(secs / 60), sec = secs % 60;
      el.textContent = `working on this stage for ${m ? m + 'm ' : ''}${sec}s`;
    }, 1000);
  },

  _stopTicker() {
    if (this._tickTimer) { clearInterval(this._tickTimer); this._tickTimer = null; }
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
        mode: (p.plan && p.plan.copilot) ? 'copilot' : 'autopilot',
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

  async _pause() {
    try {
      await API.post('/pipeline/stop', {});
      Toast.info('Pausing after the current stage finishes…');
    } catch (e) { Toast.error(`Couldn't pause: ${e.message}`); }
  },

  async _resume() {
    try {
      await API.post('/pipeline/resume', { run_id: this._detail.run_id });
      Toast.success('Resuming your paper.');
      this._detail = await API.get(`/papers/${this._detail.id}`);
      this._renderDetail();
      this._startPolling();
    } catch (e) {
      Toast.error(String(e.message).includes('409')
        ? 'Another paper is being written right now — try again when it finishes.'
        : `Couldn't resume: ${e.message}`);
    }
  },

  async _redo(stage) {
    const note = prompt(`Redo from step ${stage}. Add any direction (optional):`, '');
    if (note === null) return;  // cancelled
    try {
      await API.post('/pipeline/redo', { run_id: this._detail.run_id, stage, guidance: note || '' });
      Toast.success(`Re-running from step ${stage}.`);
      this._detail = await API.get(`/papers/${this._detail.id}`);
      this._renderDetail();
      this._startPolling();
    } catch (e) {
      Toast.error(String(e.message).includes('409')
        ? 'Another paper is being written right now — try again when it finishes.'
        : `Couldn't redo: ${e.message}`);
    }
  },

  async _gate(decision, guidance) {
    try {
      await API.post('/pipeline/gate', { run_id: this._detail.run_id, decision, guidance: guidance || '' });
      this._status_waiting = null;
      const host = document.getElementById('gate-card');
      if (host) host.innerHTML = '';
      Toast.success(decision === 'reject' ? 'Stopping the run.' : 'Continuing…');
    } catch (e) { Toast.error(`Couldn't send that: ${e.message}`); }
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
