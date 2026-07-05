/**
 * Toast — small non-blocking notifications (replaces alert()).
 */
const Toast = {
  _root() {
    let el = document.getElementById('toast-root');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast-root';
      document.body.appendChild(el);
    }
    return el;
  },

  show(message, kind = 'info', ms = 5000) {
    const t = document.createElement('div');
    t.className = `g-toast ${kind}`;
    t.innerHTML = `<span style="flex:1">${message}</span>
      <button style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:14px;padding:0">✕</button>`;
    t.querySelector('button').addEventListener('click', () => t.remove());
    this._root().appendChild(t);
    if (ms) setTimeout(() => t.remove(), ms);
    return t;
  },

  success(msg, ms) { return this.show(msg, 'success', ms); },
  error(msg, ms) { return this.show(msg, 'error', ms === undefined ? 8000 : ms); },
  info(msg, ms) { return this.show(msg, 'info', ms); },
};
