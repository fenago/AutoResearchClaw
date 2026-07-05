/**
 * Account — who you are + change your password.
 */
const Account = {
  render(container) {
    if (!Auth.cfg || !Auth.cfg.enabled) {
      container.innerHTML = `<div class="card" style="max-width:520px;margin:0 auto">
        <h2>👤 Account</h2>
        <p style="color:var(--text-muted);font-size:13px;margin-top:10px">Sign-in is not enabled on this server.</p>
      </div>`;
      return;
    }
    container.innerHTML = `
      <div class="card" style="max-width:520px;margin:0 auto">
        <h2 style="margin-bottom:4px">👤 Account</h2>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px">
          Signed in as <span style="color:var(--accent);font-weight:600">${Auth.email() || 'unknown'}</span></p>

        <h3 style="font-size:14px;margin-bottom:10px">Change password</h3>
        <form id="pw-form" style="display:flex;flex-direction:column;gap:10px;max-width:360px">
          <input id="pw-new" class="g-input" type="password" required minlength="8"
            placeholder="new password (min 8 characters)" autocomplete="new-password" />
          <input id="pw-confirm" class="g-input" type="password" required
            placeholder="confirm new password" autocomplete="new-password" />
          <button type="submit" class="g-btn primary" style="align-self:flex-start">Change password</button>
        </form>
        <p id="pw-status" style="font-size:13px;margin-top:10px;min-height:18px"></p>

        <div style="border-top:1px solid var(--glass-border);margin-top:20px;padding-top:16px">
          <button id="account-signout" class="g-btn subtle danger">Sign out</button>
        </div>
      </div>
    `;
    const status = (msg, ok) => {
      const el = document.getElementById('pw-status');
      el.textContent = msg;
      el.style.color = ok ? 'var(--success)' : 'var(--error)';
    };
    document.getElementById('pw-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const pw = document.getElementById('pw-new').value;
      const confirm = document.getElementById('pw-confirm').value;
      if (pw !== confirm) { status("Those don't match — try again.", false); return; }
      if (pw.length < 8) { status('Use at least 8 characters.', false); return; }
      try {
        await Auth.changePassword(pw);
        document.getElementById('pw-form').reset();
        status('✓ Password changed. Use the new one next time you sign in.', true);
        Toast.success('Password changed.');
      } catch (ex) {
        status(`✗ ${ex.message}`, false);
      }
    });
    document.getElementById('account-signout').addEventListener('click', () => Auth.logout());
  },
};
