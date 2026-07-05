/**
 * UserAdmin — manage who can access this deployment (admins only).
 */
const UserAdmin = {
  _data: null,

  async render(container) {
    container.innerHTML = `
      <div class="card" style="max-width:680px">
        <h2>Users</h2>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">
          Whitelist who can sign in. Optionally create the login account with a temporary password.
        </p>
        <div id="admin-users-body">Loading...</div>
        <div id="admin-users-status" style="margin-top:12px;font-size:13px"></div>
      </div>
    `;
    await this.refresh();
  },

  async refresh() {
    const el = document.getElementById('admin-users-body');
    try {
      this._data = await API.get('/admin/users');
    } catch (e) {
      if (el) el.innerHTML = `<p style="color:var(--error)">Failed to load: ${e.message}</p>`;
      return;
    }
    if (!el) return;

    if (!this._data.is_admin) {
      el.innerHTML = `<p style="color:var(--text-muted)">Signed in as ${this._data.me || 'unknown'} — this page is for admins only.</p>`;
      return;
    }

    const inputStyle = 'padding:8px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:var(--radius)';
    el.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:16px">
        <div>
          ${this._data.users.map(u => `
            <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:6px">
              <span style="font-family:var(--font-mono);font-size:13px">${u.email}</span>
              ${u.is_admin ? '<span class="status-badge running" style="font-size:11px">admin</span>' : ''}
              <div style="flex:1"></div>
              <span style="font-size:11px;color:var(--text-muted)">${(u.added_at || '').slice(0, 10)}</span>
              ${u.email === this._data.me ? '' : `<button class="admin-remove" data-email="${u.email}"
                style="padding:3px 10px;font-size:12px;background:transparent;color:var(--error);border:1px solid var(--border);border-radius:6px;cursor:pointer">Remove</button>`}
            </div>
          `).join('')}
        </div>

        <div style="border-top:1px solid var(--border);padding-top:16px">
          <h3 style="font-size:14px;margin-bottom:10px">Add user</h3>
          <div style="display:flex;flex-direction:column;gap:8px;max-width:420px">
            <input id="admin-new-email" type="email" placeholder="email" style="${inputStyle}" />
            <input id="admin-new-password" type="text" placeholder="temp password (optional — creates the account too)"
              autocomplete="off" data-lpignore="true" data-1p-ignore style="${inputStyle}" />
            <label style="font-size:13px;display:flex;align-items:center;gap:6px">
              <input id="admin-new-isadmin" type="checkbox" /> Admin
            </label>
            <button id="admin-add-btn" class="btn primary" style="padding:8px 16px;align-self:flex-start">Add user</button>
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin-top:10px">
            With a temp password, the account is created and the user receives a confirmation
            email — after confirming, they sign in with the temp password. Without one, the
            email is whitelisted and must belong to an existing account.
          </p>
        </div>
      </div>
    `;

    document.getElementById('admin-add-btn').addEventListener('click', () => this._add());
    el.querySelectorAll('.admin-remove').forEach(btn => {
      btn.addEventListener('click', () => this._remove(btn.dataset.email));
    });
  },

  _status(msg, ok) {
    const el = document.getElementById('admin-users-status');
    if (el) el.innerHTML = msg ? `<span style="color:${ok ? 'var(--success)' : 'var(--error)'}">${msg}</span>` : '';
  },

  async _add() {
    const email = document.getElementById('admin-new-email').value.trim();
    if (!email) { this._status('Enter an email.', false); return; }
    try {
      const res = await API.post('/admin/users', {
        email,
        is_admin: document.getElementById('admin-new-isadmin').checked,
        temp_password: document.getElementById('admin-new-password').value.trim(),
      });
      this._status(`✓ ${res.email} added. ${res.note}`, true);
      await this.refresh();
    } catch (e) {
      this._status(`✗ ${e.message}`, false);
    }
  },

  async _remove(email) {
    if (!confirm(`Remove ${email} from the allowlist?`)) return;
    try {
      await fetch(`/api/admin/users?email=${encodeURIComponent(email)}`, {
        method: 'DELETE',
        headers: API._authHeaders(),
      }).then(async r => { if (!r.ok) throw new Error(await r.text()); });
      this._status(`✓ ${email} removed`, true);
      await this.refresh();
    } catch (e) {
      this._status(`✗ ${e.message}`, false);
    }
  },
};
