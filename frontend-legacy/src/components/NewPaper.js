/**
 * NewPaper — the dead-simple front door: describe your idea, confirm the
 * AI-drafted plan, start the pipeline. No technical setup.
 */
const NP_STAGES = [
  [1,'Understanding your idea'],[2,'Breaking it into research questions'],[3,'Planning the literature search'],
  [4,'Collecting papers'],[5,'Screening for relevance'],[6,'Extracting key findings'],
  [7,"Synthesizing what's known"],[8,'Forming the hypothesis'],[9,'Designing the experiments'],
  [10,'Writing the experiment code'],[11,'Planning compute resources'],[12,'Running the experiments'],
  [13,'Refining the experiments'],[14,'Analyzing the results'],[15,'Deciding how to proceed'],
  [16,'Outlining the paper'],[17,'Writing the draft'],[18,'Running peer review'],
  [19,'Revising the paper'],[20,'Final quality checks'],[21,'Archiving what was learned'],
  [22,'Exporting the deliverables'],[23,'Verifying every citation'],
];
const NP_KEY_GATES = [5, 9, 20];

const NewPaper = {
  _plan: null,
  _idea: '',
  _gateLevel: 'gates',       // 'gates' | 'every' | 'custom'
  _customGates: [5, 9, 20],

  render(container) {
    this._container = container;
    if (this._plan) this._renderConfirm();
    else this._renderIdea();
    this._loadUsage();
  },

  async _loadUsage() {
    try {
      this._usage = await API.get('/me/usage');
      this._renderUsageBadge();
    } catch (e) { /* non-fatal */ }
  },

  _usageText() {
    const u = this._usage;
    if (!u || !u.enabled) return '';
    if (u.is_admin) return `${u.used} papers this month · unlimited`;
    return `${u.used} of ${u.limit} papers used this month · ${u.remaining} left`;
  },

  _renderUsageBadge() {
    const el = document.getElementById('np-usage');
    if (!el) return;
    const u = this._usage;
    if (!u || !u.enabled) { el.textContent = ''; return; }
    const low = !u.is_admin && u.remaining <= 3;
    el.innerHTML = `<span class="g-pill" style="color:${low ? 'var(--error)' : 'var(--text-muted)'}">${this._usageText()}</span>`;
  },

  _inputStyle: 'padding:12px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius);font-size:15px;font-family:var(--font-sans)',

  _renderIdea() {
    this._container.innerHTML = `
      <div class="card" style="max-width:680px;margin:0 auto">
        <div style="display:flex;align-items:flex-start;gap:12px">
          <h2 style="margin-bottom:4px;flex:1">✍️ New Paper</h2>
          <span id="np-usage"></span>
        </div>
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

          ${p.research_type ? `<div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">Type of research</div>
          <div style="font-size:14px;margin:2px 0 14px">
            <span style="display:inline-block;padding:2px 10px;border-radius:999px;background:var(--glass-highlight);border:1px solid var(--glass-border);font-size:12.5px;font-weight:600;color:var(--accent)">${p.research_type.paradigm || ''}${p.research_type.design ? ' · ' + p.research_type.design : ''}</span>
            <div style="color:var(--text-secondary);margin-top:5px">${p.research_type.summary || ''}</div>
          </div>` : ''}

          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">What the paper will find out</div>
          <div style="font-size:14px;margin:2px 0 14px">${p.goal}</div>

          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">How I'll get there</div>
          <ul style="margin:6px 0 0 18px;font-size:14px;color:var(--text-secondary)">
            ${(p.approach || []).map(a => `<li style="margin-bottom:4px">${a}</li>`).join('')}
          </ul>
        </div>

        <div style="margin-top:18px">
          <div style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">How involved do you want to be?</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <label class="mode-opt" style="flex:1;min-width:220px;border:1px solid var(--glass-border);border-radius:12px;padding:12px 14px;cursor:pointer;display:flex;gap:10px;align-items:flex-start">
              <input type="radio" name="np-mode" value="copilot" checked style="margin-top:3px" />
              <span><span style="font-weight:600">🎛️ Co-pilot</span><br><span style="font-size:12.5px;color:var(--text-muted)">Pause so you can approve or steer. You choose where.</span></span>
            </label>
            <label class="mode-opt" style="flex:1;min-width:220px;border:1px solid var(--glass-border);border-radius:12px;padding:12px 14px;cursor:pointer;display:flex;gap:10px;align-items:flex-start">
              <input type="radio" name="np-mode" value="autopilot" style="margin-top:3px" />
              <span><span style="font-weight:600">🚀 Autopilot</span><br><span style="font-size:12.5px;color:var(--text-muted)">Run start to finish on its own. Watch anytime.</span></span>
            </label>
          </div>

          <div id="np-gate-panel" style="margin-top:12px;border:1px solid var(--glass-border);border-radius:12px;padding:14px;background:var(--glass-highlight)">
            <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Where should I pause for your approval?</div>
            <div style="display:flex;flex-direction:column;gap:6px">
              <label style="display:flex;gap:8px;align-items:center;cursor:pointer;font-size:13px">
                <input type="radio" name="np-gate-level" value="gates" checked /> Only the key decisions <span style="color:var(--text-muted)">(3: literature, experiment design, quality)</span></label>
              <label style="display:flex;gap:8px;align-items:center;cursor:pointer;font-size:13px">
                <input type="radio" name="np-gate-level" value="every" /> Every step <span style="color:var(--text-muted)">(all 23 — most control)</span></label>
              <label style="display:flex;gap:8px;align-items:center;cursor:pointer;font-size:13px">
                <input type="radio" name="np-gate-level" value="custom" /> Let me choose the steps…</label>
            </div>
            <div id="np-custom-stages" style="display:none;margin-top:10px;max-height:200px;overflow-y:auto;border-top:1px solid var(--glass-border);padding-top:10px">
              ${NP_STAGES.map(([n,label]) => `<label style="display:flex;gap:8px;align-items:center;font-size:12.5px;padding:3px 0;cursor:pointer">
                <input type="checkbox" class="np-stage-ck" value="${n}" ${NP_KEY_GATES.includes(n) ? 'checked' : ''} /> <span style="color:var(--text-muted);width:22px">${n}.</span> ${label} ${NP_KEY_GATES.includes(n) ? '<span style="color:var(--accent);font-size:11px">◆ gate</span>' : ''}</label>`).join('')}
            </div>
          </div>
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
        <div style="font-size:12px;color:var(--text-muted);margin-top:10px;padding:10px 12px;border:1px solid var(--glass-border);border-radius:10px;background:var(--glass-highlight)">
          <div>⏱️ A full run takes hours and makes hundreds of AI-model calls on your configured model — you can watch every stage live and step away any time.</div>
          <div id="np-confirm-usage" style="margin-top:6px"></div>
        </div>
      </div>
    `;
    const syncGatePanel = () => {
      const mode = (document.querySelector('input[name="np-mode"]:checked') || {}).value;
      const panel = document.getElementById('np-gate-panel');
      if (panel) panel.style.display = mode === 'copilot' ? 'block' : 'none';
      const level = (document.querySelector('input[name="np-gate-level"]:checked') || {}).value;
      const custom = document.getElementById('np-custom-stages');
      if (custom) custom.style.display = level === 'custom' ? 'block' : 'none';
    };
    document.querySelectorAll('input[name="np-mode"]').forEach(r => r.addEventListener('change', syncGatePanel));
    document.querySelectorAll('input[name="np-gate-level"]').forEach(r => r.addEventListener('change', syncGatePanel));
    syncGatePanel();

    document.getElementById('np-start-btn').addEventListener('click', () => {
      const mode = (document.querySelector('input[name="np-mode"]:checked') || {}).value || 'copilot';
      this._start(this._plan.topic, this._plan, mode, this._gateStagesFromUI());
    });
    document.getElementById('np-edit-btn').addEventListener('click', () => { this._plan = null; this._renderIdea(); });
    document.getElementById('np-again-btn').addEventListener('click', () => { this._plan = null; this._renderIdea(); this._makePlanFromSaved(); });
    const cu = document.getElementById('np-confirm-usage');
    if (cu && this._usage && this._usage.enabled) {
      cu.textContent = this._usage.is_admin
        ? `This uses 1 paper — you have unlimited runs (admin).`
        : `This uses 1 of your ${this._usage.limit} monthly papers (${this._usage.remaining} left).`;
    }
  },

  async _makePlanFromSaved() {
    // re-run planning with the saved idea (textarea already filled)
    await this._makePlan();
  },

  _gateStagesFromUI() {
    const level = (document.querySelector('input[name="np-gate-level"]:checked') || {}).value || 'gates';
    if (level === 'every') return NP_STAGES.map(s => s[0]);
    if (level === 'custom') {
      return Array.from(document.querySelectorAll('.np-stage-ck:checked')).map(c => parseInt(c.value, 10));
    }
    return NP_KEY_GATES.slice();
  },

  async _start(topic, plan, mode, gateStages) {
    this._setStatus('Starting the pipeline…', true);
    try {
      const res = await API.post('/pipeline/start', {
        topic, auto_approve: true, mode: mode || 'copilot',
        gate_stages: (mode === 'copilot') ? (gateStages || NP_KEY_GATES) : null,
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
      if (String(e.message).includes('429')) {
        this._setStatus('You have reached your monthly paper limit. It resets on the 1st of the month — ask an admin if you need more.', false);
      } else if (String(e.message).includes('409')) {
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
