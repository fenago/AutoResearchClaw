/**
 * LLMSettings — choose the LLM provider, verify the key, and pick from the
 * provider's live model list (searchable).
 */
const LLMSettings = {
  _data: null,
  _models: [],        // live-fetched models for the selected provider
  _selectedModel: '',

  async render(container) {
    container.innerHTML = `
      <div class="card" style="max-width:680px">
        <h2>LLM Settings</h2>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">
          1. Pick a provider &nbsp;→&nbsp; 2. Enter your API key and load its models &nbsp;→&nbsp; 3. Pick a model and save.
        </p>
        <div id="llm-settings-form">Loading...</div>
        <div id="llm-settings-status" style="margin-top:12px;font-size:13px"></div>
      </div>
    `;
    try {
      this._data = await API.get('/llm/settings');
      this._renderForm();
    } catch (e) {
      const el = document.getElementById('llm-settings-form');
      if (el) el.innerHTML = `<p style="color:var(--error,#e5534b)">Failed to load settings: ${e.message}</p>`;
    }
  },

  _inputStyle: 'padding:8px;background:var(--bg-input,var(--bg-tertiary));color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)',

  _renderForm() {
    const el = document.getElementById('llm-settings-form');
    if (!el || !this._data) return;
    const { current, providers } = this._data;
    this._selectedModel = current.model || '';

    el.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:14px">
        <label style="display:flex;flex-direction:column;gap:4px;font-size:13px">
          Provider
          <select id="llm-provider" style="${this._inputStyle}">
            ${providers.map(p => `<option value="${p.id}" ${p.id === current.provider ? 'selected' : ''}>${p.label}</option>`).join('')}
          </select>
        </label>

        <label style="display:flex;flex-direction:column;gap:4px;font-size:13px">
          API key <span id="llm-key-hint" style="color:var(--text-muted)"></span>
          <div style="display:flex;gap:8px">
            <input id="llm-api-key" type="password" placeholder="paste key (blank = use key already on server)"
              style="${this._inputStyle};flex:1" />
            <button id="llm-load-models" class="btn primary" style="padding:8px 14px;white-space:nowrap">Test key &amp; load models</button>
          </div>
        </label>

        <div id="llm-model-picker" style="display:flex;flex-direction:column;gap:6px">
          <label style="font-size:13px;display:flex;justify-content:space-between">
            <span>Model <span id="llm-model-count" style="color:var(--text-muted)"></span></span>
            <span id="llm-model-selected" style="color:var(--accent);font-family:var(--font-mono);font-size:12px"></span>
          </label>
          <input id="llm-model-search" type="text" placeholder="search models… (or type an exact model id)"
            style="${this._inputStyle}" />
          <div id="llm-model-list"
            style="max-height:260px;overflow-y:auto;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg-tertiary)"></div>
        </div>

        <div style="display:flex;gap:8px">
          <button id="llm-save" class="btn primary" style="padding:8px 16px">Save</button>
          <button id="llm-test" class="btn" style="padding:8px 16px">Test chat</button>
        </div>
      </div>
    `;

    document.getElementById('llm-provider').addEventListener('change', () => {
      this._models = [];
      this._selectedModel = '';
      document.getElementById('llm-api-key').value = '';
      this._renderModelList();
      this._updateKeyHint();
      this._status('', true);
    });
    document.getElementById('llm-load-models').addEventListener('click', () => this._loadModels());
    document.getElementById('llm-model-search').addEventListener('input', () => this._renderModelList());
    document.getElementById('llm-save').addEventListener('click', () => this._save());
    document.getElementById('llm-test').addEventListener('click', () => this._test());

    this._updateKeyHint();
    this._renderModelList();

    // If a key is already available server-side, load models right away.
    const p = providers.find(x => x.id === document.getElementById('llm-provider').value);
    if (p && p.has_api_key) this._loadModels(true);
  },

  _updateKeyHint() {
    const hint = document.getElementById('llm-key-hint');
    const p = this._data.providers.find(x => x.id === document.getElementById('llm-provider').value);
    if (hint && p) {
      hint.textContent = p.has_api_key
        ? `(a ${p.label} key is already configured on the server — leave blank to use it)`
        : `(no server key — paste yours, or set ${p.api_key_env})`;
    }
  },

  async _loadModels(quiet) {
    const btn = document.getElementById('llm-load-models');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }
    if (!quiet) this._status('Contacting provider…', true);
    try {
      const res = await API.post('/llm/models', {
        provider: document.getElementById('llm-provider').value,
        api_key: document.getElementById('llm-api-key').value.trim(),
      });
      if (res.ok) {
        this._models = res.models;
        this._status(`✓ Key works — ${res.count} models available`, true);
      } else {
        this._models = [];
        if (!quiet) this._status(`✗ ${res.error}`, false);
      }
    } catch (e) {
      if (!quiet) this._status(`✗ ${e.message}`, false);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Test key &amp; load models'; }
      this._renderModelList();
    }
  },

  _renderModelList() {
    const list = document.getElementById('llm-model-list');
    const count = document.getElementById('llm-model-count');
    const sel = document.getElementById('llm-model-selected');
    if (!list) return;

    const q = (document.getElementById('llm-model-search').value || '').trim().toLowerCase();
    const filtered = this._models.filter(m => m.toLowerCase().includes(q));

    if (count) count.textContent = this._models.length ? `— ${filtered.length}/${this._models.length}` : '';
    if (sel) sel.textContent = this._selectedModel || '';

    let rows = filtered.slice(0, 500).map(m => `
      <div class="llm-model-row" data-model="${m}"
        style="padding:6px 10px;cursor:pointer;font-family:var(--font-mono);font-size:12px;
               ${m === this._selectedModel ? 'background:var(--bg-secondary);color:var(--accent)' : ''}">${m}</div>
    `).join('');

    if (!this._models.length) {
      rows = `<div style="padding:10px;color:var(--text-muted);font-size:13px">
        No models loaded yet — enter your API key and click "Test key &amp; load models".</div>`;
    } else if (!filtered.length && q) {
      rows = `<div class="llm-model-row" data-model="${q}"
        style="padding:6px 10px;cursor:pointer;font-size:13px;color:var(--text-secondary)">
        No match — use "<span style="font-family:var(--font-mono)">${q}</span>" as a custom model id</div>`;
    }
    list.innerHTML = rows;

    list.querySelectorAll('.llm-model-row').forEach(row => {
      row.addEventListener('click', () => {
        this._selectedModel = row.dataset.model;
        this._renderModelList();
      });
    });
  },

  _status(msg, ok) {
    const el = document.getElementById('llm-settings-status');
    if (el) el.innerHTML = msg
      ? `<span style="color:${ok ? 'var(--success,#3fb950)' : 'var(--error,#e5534b)'}">${msg}</span>` : '';
  },

  async _save() {
    const model = this._selectedModel || (document.getElementById('llm-model-search').value || '').trim();
    if (!model) { this._status('Pick a model from the list (or type an exact id in the search box).', false); return; }
    try {
      const res = await API.post('/llm/settings', {
        provider: document.getElementById('llm-provider').value,
        model,
        api_key: document.getElementById('llm-api-key').value.trim(),
      });
      this._status(`Saved — using ${res.current.provider} / ${model}`, true);
      this._data = await API.get('/llm/settings');
      this._updateKeyHint();
    } catch (e) {
      this._status(`Save failed: ${e.message}`, false);
    }
  },

  async _test() {
    this._status('Sending a test message…', true);
    try {
      const res = await API.post('/llm/test', {});
      if (res.ok) this._status(`✓ ${res.model} responded${res.reply ? `: "${res.reply}"` : ''}`, true);
      else this._status(`✗ ${res.error}`, false);
    } catch (e) {
      this._status(`Test failed: ${e.message}`, false);
    }
  },
};
