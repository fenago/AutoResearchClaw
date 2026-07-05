/**
 * NewPaper — the dead-simple front door: describe your idea, confirm the
 * AI-drafted plan, start the pipeline. No technical setup.
 */
const NewPaper = {
  _plan: null,
  _idea: '',

  render(container) {
    this._container = container;
    if (this._plan) this._renderConfirm();
    else this._renderIdea();
  },

  _inputStyle: 'padding:12px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius);font-size:15px;font-family:var(--font-sans)',

  _renderIdea() {
    this._container.innerHTML = `
      <div class="card" style="max-width:680px;margin:0 auto">
        <h2 style="margin-bottom:4px">✍️ New Paper</h2>
        <p style="color:var(--text-secondary);font-size:14px;margin-bottom:18px">
          Tell me your idea and what you want the paper to accomplish — in plain English.
          I'll draft a plan for you to confirm, then do the rest: literature review,
          experiments, analysis, and the finished paper.
        </p>
        <textarea id="np-idea" rows="6" style="${this._inputStyle};width:100%;resize:vertical"
          placeholder="e.g. I think smaller AI models fine-tuned on high-quality data can beat much bigger ones on medical question answering. I want a paper that tests this and shows when it's true."></textarea>
        <div style="display:flex;gap:10px;margin-top:14px;align-items:center">
          <button id="np-plan-btn" class="btn primary"
            style="padding:10px 22px;font-size:15px;border:none;border-radius:8px;cursor:pointer;background:var(--accent);color:#fff;font-weight:600">
            Draft my plan →</button>
          <span id="np-status" style="font-size:13px;color:var(--text-muted)"></span>
        </div>
      </div>
    `;
    const ta = document.getElementById('np-idea');
    ta.value = this._idea || '';
    document.getElementById('np-plan-btn').addEventListener('click', () => this._makePlan());
  },

  async _makePlan() {
    const idea = document.getElementById('np-idea').value.trim();
    if (!idea) { this._setStatus('Type your idea first.', false); return; }
    this._idea = idea;
    const btn = document.getElementById('np-plan-btn');
    btn.disabled = true; btn.textContent = 'Thinking…';
    this._setStatus('Turning your idea into a research plan (10–30s)…', true);
    try {
      const res = await API.post('/paper/plan', { idea });
      if (!res.ok) {
        this._setStatus(`Couldn't draft a plan: ${res.error}. Check ⚙️ LLM Settings, or start directly below.`, false);
        this._offerDirectStart(idea);
        return;
      }
      this._plan = res.plan;
      this._renderConfirm();
    } catch (e) {
      this._setStatus(`Error: ${e.message}`, false);
    } finally {
      if (document.getElementById('np-plan-btn')) {
        btn.disabled = false; btn.textContent = 'Draft my plan →';
      }
    }
  },

  _offerDirectStart(idea) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'margin-top:12px';
    wrap.innerHTML = `<button id="np-direct-btn" style="padding:8px 16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-tertiary);color:var(--text-primary);cursor:pointer">Start research with my idea as-is</button>`;
    this._container.querySelector('.card').appendChild(wrap);
    document.getElementById('np-direct-btn').addEventListener('click', () => this._start(idea));
  },

  _renderConfirm() {
    const p = this._plan;
    this._container.innerHTML = `
      <div class="card" style="max-width:680px;margin:0 auto">
        <h2 style="margin-bottom:4px">Here's the plan — look right?</h2>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:18px">Nothing starts until you confirm. The experiments decide the answer — if the evidence points the other way, that's what the paper will say.</p>

        <div style="border:1px solid var(--border);border-radius:var(--radius);padding:18px;background:var(--bg-tertiary)">
          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">Working title</div>
          <div style="font-size:18px;font-weight:600;color:var(--accent);margin:2px 0 14px">${p.title}</div>

          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">The hypothesis we'll test</div>
          <div style="font-size:14px;margin:2px 0 14px">${p.hypothesis || ''}</div>

          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">What the paper will find out</div>
          <div style="font-size:14px;margin:2px 0 14px">${p.goal}</div>

          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">How I'll get there</div>
          <ul style="margin:6px 0 0 18px;font-size:14px;color:var(--text-secondary)">
            ${(p.approach || []).map(a => `<li style="margin-bottom:4px">${a}</li>`).join('')}
          </ul>
        </div>

        <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap;align-items:center">
          <button id="np-start-btn"
            style="padding:11px 24px;font-size:15px;border:none;border-radius:8px;cursor:pointer;background:var(--success);color:#fff;font-weight:600">
            ✓ Yes — start my paper</button>
          <button id="np-edit-btn"
            style="padding:11px 16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-tertiary);color:var(--text-primary);cursor:pointer">✏️ Change my idea</button>
          <button id="np-again-btn"
            style="padding:11px 16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-tertiary);color:var(--text-primary);cursor:pointer">🔁 Redraft</button>
        </div>
        <p id="np-status" style="font-size:13px;margin-top:12px;color:var(--text-muted)"></p>
        <p style="font-size:12px;color:var(--text-muted);margin-top:8px">
          Heads up: a full run takes a while (hours, not minutes) and makes many AI-model calls.
          You can watch every stage live and step away any time.</p>
      </div>
    `;
    document.getElementById('np-start-btn').addEventListener('click', () => this._start(this._plan.topic, this._plan));
    document.getElementById('np-edit-btn').addEventListener('click', () => { this._plan = null; this._renderIdea(); });
    document.getElementById('np-again-btn').addEventListener('click', () => { this._plan = null; this._renderIdea(); this._makePlanFromSaved(); });
  },

  async _makePlanFromSaved() {
    // re-run planning with the saved idea (textarea already filled)
    await this._makePlan();
  },

  async _start(topic, plan) {
    this._setStatus('Starting the pipeline…', true);
    try {
      const res = await API.post('/pipeline/start', {
        topic, auto_approve: true,
        title: plan ? plan.title : null, plan: plan || null,
      });
      this._plan = null;
      this._setStatus('', true);
      if (res.status === 'queued') Toast.info('⏳ Added to the queue — it starts automatically when the current paper finishes.');
      else Toast.success('🚀 Your paper is underway — here it is, live.');
      try {
        const row = await API.get(`/papers/by-run/${res.run_id}`);
        location.hash = `papers/${row.id}`;
      } catch (e2) {
        location.hash = 'mypapers';
      }
    } catch (e) {
      if (String(e.message).includes('409')) {
        this._setStatus('A paper is already being written — open 📚 My Papers to watch it. One paper runs at a time for now.', false);
      } else {
        this._setStatus(`Couldn't start: ${e.message}`, false);
      }
    }
  },

  _setStatus(msg, ok) {
    const el = document.getElementById('np-status');
    if (el) { el.textContent = msg; el.style.color = ok ? 'var(--text-muted)' : 'var(--error)'; }
  },
};
