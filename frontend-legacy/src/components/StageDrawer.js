/**
 * StageDrawer — the transparency surface for a single pipeline stage.
 * Slides in from the right when the user clicks a stage, and shows what
 * that stage does, the AI's reasoning, and every file it produced.
 *
 * Public API:
 *   StageDrawer.open(paperId, stageNum)  — open the drawer for that stage
 *   StageDrawer.close()                  — close it
 */
const StageDrawer = {
  _paperId: null,
  _stageNum: null,
  _stage: null,
  _tab: 'what',
  _fileCache: {},
  _openToken: 0,

  /* ---------- public API ---------- */

  async open(paperId, stageNum) {
    this._paperId = paperId;
    this._stageNum = stageNum;
    this._stage = null;
    this._tab = 'what';
    const token = ++this._openToken;

    this._ensureDom();
    this._show();
    this._body.innerHTML = `<div style="padding:28px 22px;color:var(--text-muted);font-size:13px">Loading stage details…</div>`;

    try {
      const res = await API.get('/paper/' + paperId + '/stages');
      if (token !== this._openToken) return; // a newer open() superseded us
      const stage = (res.stages || []).find(s => Number(s.num) === Number(stageNum));
      if (!stage) {
        this._body.innerHTML = `<div style="padding:28px 22px;color:var(--text-secondary);font-size:13px">
          Couldn't find stage ${this._esc(String(stageNum))} for this paper.</div>`;
        return;
      }
      this._stage = stage;
      this._render();
    } catch (e) {
      if (token !== this._openToken) return;
      this._body.innerHTML = `<div style="padding:28px 22px;font-size:13px;color:var(--text-secondary)">
        Couldn't load this stage: ${this._esc(e.message || String(e))}
        <div style="color:var(--text-muted);margin-top:6px">Close the panel and try again.</div></div>`;
    }
  },

  close() {
    this._openToken++;
    if (!this._panel) return;
    this._panel.classList.remove('sd-open');
    this._backdrop.classList.remove('sd-open');
    clearTimeout(this._hideTimer);
    this._hideTimer = setTimeout(() => {
      if (this._panel && !this._panel.classList.contains('sd-open')) {
        this._panel.style.display = 'none';
        this._backdrop.style.display = 'none';
      }
    }, 320); // matches the CSS transition
  },

  /* ---------- overlay scaffolding (created once) ---------- */

  _ensureDom() {
    if (this._panel) return;

    if (!document.getElementById('stage-drawer-style')) {
      const style = document.createElement('style');
      style.id = 'stage-drawer-style';
      style.textContent = `
        .sd-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1499;
          opacity:0;transition:opacity .3s ease}
        .sd-backdrop.sd-open{opacity:1}
        .sd-panel{position:fixed;top:0;right:0;bottom:0;width:480px;max-width:92vw;z-index:1500;
          background:var(--glass-bg);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
          border-left:1px solid var(--glass-border);box-shadow:-20px 0 50px rgba(0,0,0,.35);
          transform:translateX(100%);transition:transform .3s cubic-bezier(.22,.8,.3,1);
          display:flex;flex-direction:column;overflow:hidden}
        .sd-panel.sd-open{transform:translateX(0)}
        .sd-tab{flex:1;padding:9px 6px;font-size:12.5px;border:none;cursor:pointer;
          background:transparent;color:var(--text-muted);border-bottom:2px solid transparent}
        .sd-tab.active{color:var(--text-primary);border-bottom-color:var(--accent)}
        .sd-file-row{display:flex;align-items:center;gap:8px;padding:9px 10px;cursor:pointer;
          border:1px solid var(--glass-border);border-radius:8px;margin-bottom:6px}
        .sd-file-row:hover{background:var(--bg-tertiary)}
      `;
      document.head.appendChild(style);
    }

    this._backdrop = document.createElement('div');
    this._backdrop.className = 'sd-backdrop';
    this._backdrop.style.display = 'none';
    this._backdrop.addEventListener('click', () => this.close());

    this._panel = document.createElement('div');
    this._panel.className = 'sd-panel';
    this._panel.style.display = 'none';
    this._panel.innerHTML = `<div id="sd-body" style="flex:1;display:flex;flex-direction:column;overflow-y:auto"></div>`;

    document.body.appendChild(this._backdrop);
    document.body.appendChild(this._panel);
    this._body = this._panel.querySelector('#sd-body');

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && this._panel.classList.contains('sd-open')) this.close();
    });
  },

  _show() {
    clearTimeout(this._hideTimer);
    this._backdrop.style.display = 'block';
    this._panel.style.display = 'flex';
    // Force a layout pass so the transform transition actually animates
    void this._panel.offsetWidth;
    this._backdrop.classList.add('sd-open');
    this._panel.classList.add('sd-open');
  },

  /* ---------- rendering ---------- */

  _render() {
    const s = this._stage;
    const stateCls = { done: 'done', active: 'running', pending: 'pending' }[s.state] || 'pending';
    const stateLabel = { done: 'Done', active: 'In progress', pending: 'Not started yet' }[s.state] || s.state;

    this._body.innerHTML = `
      <div style="padding:20px 22px 0">
        <div style="display:flex;align-items:flex-start;gap:10px">
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
              <span style="font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--glass-border);color:var(--text-muted)">${this._esc(s.phase || '')}</span>
              <span class="g-pill ${stateCls}" style="font-size:11px">${this._esc(stateLabel)}</span>
              ${s.is_gate ? `<span style="font-size:11px;padding:2px 8px;border-radius:999px;background:var(--bg-tertiary);border:1px solid var(--accent);color:var(--accent)">◆ Decision point</span>` : ''}
            </div>
            <h3 style="font-size:17px;line-height:1.3;color:var(--text-primary)">
              ${this._esc(String(s.num))}. ${this._esc(s.title || s.key || '')}</h3>
            ${s.summary ? `<p style="font-size:12.5px;color:var(--text-secondary);margin-top:6px">${this._esc(s.summary)}</p>` : ''}
          </div>
          <button id="sd-close" title="Close" style="background:transparent;border:none;cursor:pointer;font-size:18px;color:var(--text-muted);padding:2px 6px;line-height:1">✕</button>
        </div>
      </div>
      <div style="display:flex;gap:2px;margin-top:16px;padding:0 22px;border-bottom:1px solid var(--glass-border)">
        <button class="sd-tab" data-tab="what">What happens here</button>
        <button class="sd-tab" data-tab="reasoning">Reasoning</button>
        <button class="sd-tab" data-tab="files">Files${(s.files || []).length ? ` (${s.files.length})` : ''}</button>
      </div>
      <div id="sd-content" style="flex:1;overflow-y:auto;padding:18px 22px 28px;font-size:13.5px;line-height:1.6;color:var(--text-secondary)"></div>
    `;

    this._body.querySelector('#sd-close').addEventListener('click', () => this.close());
    this._body.querySelectorAll('.sd-tab').forEach(btn => {
      btn.addEventListener('click', () => { this._tab = btn.dataset.tab; this._renderTab(); });
    });
    this._renderTab();
  },

  _renderTab() {
    this._body.querySelectorAll('.sd-tab').forEach(btn =>
      btn.classList.toggle('active', btn.dataset.tab === this._tab));
    const el = this._body.querySelector('#sd-content');
    if (!el) return;
    if (this._tab === 'what') this._renderWhat(el);
    else if (this._tab === 'reasoning') this._renderReasoning(el);
    else this._renderFiles(el);
  },

  /* -- tab 1: what happens here -- */

  _renderWhat(el) {
    const s = this._stage;
    el.innerHTML = `
      <p style="margin-bottom:16px">${this._esc(s.what || 'No description available for this stage.')}</p>
      <div style="padding:12px 14px;border:1px solid var(--glass-border);border-radius:10px;background:var(--bg-tertiary)">
        <div style="font-size:12.5px;margin-bottom:6px">
          <span style="color:var(--text-muted);font-weight:600">Reads:</span>
          <span style="color:var(--text-secondary)"> ${this._esc(s.reads || '—')}</span>
        </div>
        <div style="font-size:12.5px">
          <span style="color:var(--text-muted);font-weight:600">Produces:</span>
          <span style="color:var(--text-secondary)"> ${this._esc(s.produces || '—')}</span>
        </div>
      </div>
      ${s.state === 'pending' ? `
      <p style="margin-top:14px;font-size:12px;color:var(--text-muted)">
        This step hasn't run yet — once it does, its reasoning and files will appear in the other tabs.</p>` : ''}
    `;
  },

  /* -- tab 2: reasoning -- */

  async _renderReasoning(el) {
    const s = this._stage;
    const matches = this._reasoningFiles();
    if (!matches.length) {
      el.innerHTML = `<div style="text-align:center;padding:30px 0;color:var(--text-muted)">
        <div style="font-size:28px;margin-bottom:8px">💭</div>
        The reasoning will appear here once this step runs.</div>`;
      return;
    }
    el.innerHTML = `<div style="color:var(--text-muted);font-size:12.5px">Loading the reasoning…</div>`;
    const parts = [];
    for (const f of matches) {
      try {
        const res = await this._fetchFile(f.name);
        parts.push(`
          ${matches.length > 1 ? `<h4 style="font-family:var(--font-mono);font-size:12.5px;color:var(--accent);margin:${parts.length ? '20px' : '0'} 0 8px">${this._esc(f.name)}</h4>` : ''}
          ${this._renderContent(res)}`);
      } catch (e) {
        parts.push(`<p style="color:var(--text-muted);font-size:12.5px;margin-top:10px">
          Couldn't load ${this._esc(f.name)}: ${this._esc(e.message || String(e))}</p>`);
      }
    }
    if (this._tab !== 'reasoning' || this._stage !== s) return; // user moved on mid-fetch
    el.innerHTML = parts.join('');
  },

  // Files that hold this stage's reasoning: exact name match, or — for
  // directory-like names ("perspectives", "cards") — every file under that prefix.
  _reasoningFiles() {
    const s = this._stage;
    const rf = s.reasoning_file;
    const files = s.files || [];
    if (!rf) return [];
    const exact = files.filter(f => f.name === rf);
    if (exact.length) return exact;
    return files.filter(f => f.name.indexOf(rf) === 0);
  },

  /* -- tab 3: files -- */

  _renderFiles(el) {
    const files = (this._stage.files || []);
    if (!files.length) {
      el.innerHTML = `<div style="text-align:center;padding:30px 0;color:var(--text-muted)">
        <div style="font-size:28px;margin-bottom:8px">🗂</div>
        No files yet — they'll show up here as this step produces them.</div>`;
      return;
    }
    el.innerHTML = `
      <div id="sd-file-list">
        ${files.map((f, i) => `
          <div class="sd-file-row" data-idx="${i}">
            <span style="flex:1;font-family:var(--font-mono);font-size:12.5px;color:var(--text-primary);word-break:break-all">
              ${f.is_reasoning ? '⭐ ' : ''}${this._esc(f.name)}</span>
            <a href="#" class="sd-dl" data-idx="${i}" style="font-size:11.5px;color:var(--accent);text-decoration:none;flex-shrink:0">⬇ Download</a>
          </div>`).join('')}
      </div>
      <div id="sd-file-view"></div>
    `;
    el.querySelectorAll('.sd-file-row').forEach(row => {
      row.addEventListener('click', () => this._openFile(files[Number(row.dataset.idx)], el));
    });
    el.querySelectorAll('.sd-dl').forEach(a => {
      a.addEventListener('click', async e => {
        e.preventDefault();
        e.stopPropagation(); // don't also open the row
        const f = files[Number(a.dataset.idx)];
        try {
          const res = await this._fetchFile(f.name);
          this._download(f.name.split('/').pop(), res.content || '');
        } catch (err) {
          Toast.error(`Couldn't download ${f.name}: ${err.message}`);
        }
      });
    });
  },

  async _openFile(file, el) {
    const list = el.querySelector('#sd-file-list');
    const view = el.querySelector('#sd-file-view');
    if (!list || !view) return;
    list.style.display = 'none';
    view.innerHTML = `<div style="color:var(--text-muted);font-size:12.5px">Loading ${this._esc(file.name)}…</div>`;
    let inner;
    try {
      const res = await this._fetchFile(file.name);
      inner = this._renderContent(res);
    } catch (e) {
      inner = `<p style="color:var(--text-muted);font-size:12.5px">Couldn't load this file: ${this._esc(e.message || String(e))}</p>`;
    }
    view.innerHTML = `
      <a href="#" id="sd-back" style="display:inline-block;font-size:12.5px;color:var(--accent);text-decoration:none;margin-bottom:10px">← Back to file list</a>
      <div style="font-family:var(--font-mono);font-size:12px;color:var(--text-muted);margin-bottom:10px;word-break:break-all">
        ${file.is_reasoning ? '⭐ ' : ''}${this._esc(file.name)}</div>
      ${inner}`;
    view.querySelector('#sd-back').addEventListener('click', e => {
      e.preventDefault();
      view.innerHTML = '';
      list.style.display = '';
    });
  },

  /* ---------- data + content helpers ---------- */

  async _fetchFile(relpath) {
    const key = this._paperId + ':' + this._stage.num + ':' + relpath;
    if (this._fileCache[key]) return this._fileCache[key];
    const res = await API.get('/paper/' + this._paperId + '/file?stage=' + this._stage.num
      + '&name=' + encodeURIComponent(relpath));
    this._fileCache[key] = res;
    return res;
  },

  // {name, content, kind} → HTML: markdown gets the mini renderer, everything
  // else (.json/.yaml/.bib/plain text) a wrapped <pre>.
  _renderContent(res) {
    const name = res.name || '';
    const isMd = res.kind === 'markdown' || res.kind === 'md' || /\.(md|markdown)$/i.test(name);
    if (isMd) return this._md(res.content || '');
    return `<pre style="white-space:pre-wrap;overflow-x:auto;font-family:var(--font-mono);font-size:12.5px;background:var(--bg-tertiary);padding:12px;border-radius:8px">${this._esc(res.content || '')}</pre>`;
  },

  _download(name, content) {
    const blob = new Blob([content], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  },

  _esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  },

  // Minimal self-contained markdown renderer (headers, bold, italics, code,
  // lists, paragraphs). Everything is escaped before formatting is applied.
  _md(src) {
    const lines = this._esc(src).split('\n');
    let html = '', inList = false, inCode = false;
    for (const line of lines) {
      if (line.trim().indexOf('```') === 0) {
        if (inList) { html += '</ul>'; inList = false; }
        html += inCode ? '</pre>' : '<pre style="white-space:pre-wrap;overflow-x:auto;font-family:var(--font-mono);font-size:12.5px;background:var(--bg-tertiary);padding:12px;border-radius:8px">';
        inCode = !inCode; continue;
      }
      if (inCode) { html += line + '\n'; continue; }
      const fmt = t => t
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code style="background:var(--bg-tertiary);padding:1px 5px;border-radius:4px;font-family:var(--font-mono);font-size:.9em">$1</code>');
      const h = line.match(/^(#{1,6})\s+(.*)/);
      if (h) {
        if (inList) { html += '</ul>'; inList = false; }
        const level = Math.min(h[1].length + 3, 6); // # → h4, ## → h5, ### and deeper → h6
        html += `<h${level} style="margin:16px 0 6px;color:var(--text-primary);font-size:${level === 4 ? 15 : level === 5 ? 13.5 : 12.5}px">${fmt(h[2])}</h${level}>`;
        continue;
      }
      if (/^\s*[-*]\s+/.test(line)) {
        if (!inList) { html += '<ul style="margin:8px 0 8px 20px">'; inList = true; }
        html += `<li style="margin-bottom:3px">${fmt(line.replace(/^\s*[-*]\s+/, ''))}</li>`;
        continue;
      }
      if (inList) { html += '</ul>'; inList = false; }
      if (line.trim() === '') continue;
      html += `<p style="margin:7px 0">${fmt(line)}</p>`;
    }
    if (inList) html += '</ul>';
    if (inCode) html += '</pre>';
    return html;
  },
};
