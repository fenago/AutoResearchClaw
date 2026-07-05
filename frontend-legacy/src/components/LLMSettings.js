/**
 * LLMSettings — choose the LLM provider, model, and API key.
 */
const LLMSettings = {
  _data: null,

  async render(container) {
    container.innerHTML = `
      <div class="card" style="max-width:640px">
        <h2>LLM Settings</h2>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">
          Choose which provider and model power chat and pipeline runs.
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

  _renderForm() {
    const el = document.getElementById('llm-settings-form');
    if (!el || !this._data) return;
    const { current, providers } = this._data;

    el.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:14px">
        <label style="display:flex;flex-direction:column;gap:4px;font-size:13px">
          Provider
          <select id="llm-provider" class="input" style="padding:8px;background:var(--bg-input,var(--bg));color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)">
            ${providers.map(p => `<option value="${p.id}" ${p.id === current.provider ? 'selected' : ''}>${p.label}</option>`).join('')}
          </select>
        </label>

        <label style="display:flex;flex-direction:column;gap:4px;font-size:13px">
          Model
          <select id="llm-model" class="input" style="padding:8px;background:var(--bg-input,var(--bg));color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)"></select>
        </label>

        <label id="llm-custom-model-wrap" style="display:none;flex-direction:column;gap:4px;font-size:13px">
          Custom model name
          <input id="llm-custom-model" type="text" placeholder="exact model id"
            style="padding:8px;background:var(--bg-input,var(--bg));color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)" />
        </label>

        <label style="display:flex;flex-direction:column;gap:4px;font-size:13px">
          API key <span id="llm-key-hint" style="color:var(--text-muted)"></span>
          <input id="llm-api-key" type="password" placeholder="leave blank to keep current / use server env var"
            style="padding:8px;background:var(--bg-input,var(--bg));color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)" />
        </label>

        <div style="display:flex;gap:8px">
          <button id="llm-save" class="btn primary" style="padding:8px 16px">Save</button>
          <button id="llm-test" class="btn" style="padding:8px 16px">Test connection</button>
        </div>
      </div>
    `;

    const providerSel = document.getElementById('llm-provider');
    const modelSel = document.getElementById('llm-model');

    const fillModels = () => {
      const p = providers.find(x => x.id === providerSel.value);
      const models = p ? p.models : [];
      const selected = (p && p.id === current.provider && current.model) ? current.model : models[0];
      modelSel.innerHTML = models.map(m => `<option value="${m}" ${m === selected ? 'selected' : ''}>${m}</option>`).join('')
        + `<option value="__custom__">Custom…</option>`;
      if (selected && !models.includes(selected)) {
        modelSel.value = '__custom__';
        document.getElementById('llm-custom-model').value = selected;
      }
      this._toggleCustom();
      this._updateKeyHint();
    };

    providerSel.addEventListener('change', fillModels);
    modelSel.addEventListener('change', () => this._toggleCustom());
    document.getElementById('llm-save').addEventListener('click', () => this._save());
    document.getElementById('llm-test').addEventListener('click', () => this._test());
    fillModels();
  },

  _toggleCustom() {
    const wrap = document.getElementById('llm-custom-model-wrap');
    const modelSel = document.getElementById('llm-model');
    if (wrap && modelSel) wrap.style.display = modelSel.value === '__custom__' ? 'flex' : 'none';
  },

  _updateKeyHint() {
    const providerSel = document.getElementById('llm-provider');
    const hint = document.getElementById('llm-key-hint');
    const p = this._data.providers.find(x => x.id === providerSel.value);
    if (hint && p) {
      hint.textContent = p.has_api_key
        ? `(a key for ${p.label} is already configured on the server)`
        : `(no key configured — enter one, or set ${p.api_key_env} on the server)`;
    }
  },

  _selectedModel() {
    const modelSel = document.getElementById('llm-model');
    if (modelSel.value === '__custom__') {
      return document.getElementById('llm-custom-model').value.trim();
    }
    return modelSel.value;
  },

  _status(msg, ok) {
    const el = document.getElementById('llm-settings-status');
    if (el) el.innerHTML = `<span style="color:${ok ? 'var(--success,#3fb950)' : 'var(--error,#e5534b)'}">${msg}</span>`;
  },

  async _save() {
    const model = this._selectedModel();
    if (!model) { this._status('Enter a model name.', false); return; }
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
    this._status('Testing…', true);
    try {
      const res = await API.post('/llm/test', {});
      if (res.ok) this._status(`✓ Connected — ${res.model} replied: "${res.reply}"`, true);
      else this._status(`✗ ${res.error}`, false);
    } catch (e) {
      this._status(`Test failed: ${e.message}`, false);
    }
  },
};
