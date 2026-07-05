/**
 * Auth — Supabase email/password login gate (active only when the server has
 * SUPABASE_URL/SUPABASE_ANON_KEY configured).
 */
const Auth = {
  cfg: null,
  session: null,

  async init() {
    try {
      this.cfg = await (await fetch('/api/auth/config')).json();
    } catch (e) {
      this.cfg = { enabled: false };
    }
    if (!this.cfg.enabled) return true;

    try { this.session = JSON.parse(localStorage.getItem('rc_session') || 'null'); } catch (e) { this.session = null; }
    if (this.session && this.session.access_token && !this._expired()) {
      const btn = document.getElementById('logout-btn');
      if (btn) { btn.style.display = ''; btn.addEventListener('click', () => this.logout()); }
      return true;
    }
    this.showLogin();
    return false;
  },

  _expired() {
    return this.session.expires_at && (this.session.expires_at * 1000) < Date.now() + 30000;
  },

  token() {
    return (this.cfg && this.cfg.enabled && this.session) ? this.session.access_token : null;
  },

  async login(email, password) {
    const res = await fetch(`${this.cfg.url}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', apikey: this.cfg.anon_key },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error_description || data.msg || 'Login failed');
    localStorage.setItem('rc_session', JSON.stringify(data));
    location.reload();
  },

  logout() {
    localStorage.removeItem('rc_session');
    location.reload();
  },

  handleUnauthorized() {
    // Stale/revoked token or not on the allowlist — force re-login.
    localStorage.removeItem('rc_session');
    if (!document.getElementById('login-overlay')) this.showLogin();
  },

  showLogin() {
    if (document.getElementById('login-overlay')) return;
    const div = document.createElement('div');
    div.id = 'login-overlay';
    div.style.cssText = 'position:fixed;inset:0;z-index:1000;background:var(--bg-primary);display:flex;align-items:center;justify-content:center';
    div.innerHTML = `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:32px;width:340px;box-shadow:var(--shadow)">
        <h1 style="font-size:22px;margin-bottom:4px;color:var(--accent)">Sign in</h1>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px">Access is limited to invited users.</p>
        <form id="login-form" style="display:flex;flex-direction:column;gap:10px">
          <input id="login-email" type="email" required placeholder="email" autocomplete="username"
            style="padding:9px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)" />
          <input id="login-password" type="password" required placeholder="password" autocomplete="current-password"
            style="padding:9px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)" />
          <button type="submit" class="btn primary" style="padding:9px;margin-top:4px">Sign in</button>
          <div id="login-error" style="color:var(--error);font-size:12px;min-height:16px"></div>
        </form>
      </div>
    `;
    document.body.appendChild(div);
    document.getElementById('login-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const err = document.getElementById('login-error');
      err.textContent = '';
      try {
        await this.login(
          document.getElementById('login-email').value.trim(),
          document.getElementById('login-password').value,
        );
      } catch (ex) {
        err.textContent = ex.message;
      }
    });
  },
};
