/**
 * ProgressView — "Progress" in the nav: takes you to the paper being written
 * right now (or your library if nothing is running).
 */
const ProgressView = {
  async render(container) {
    container.innerHTML = `<div class="card" style="max-width:640px;margin:0 auto">
      <p style="color:var(--text-muted);font-size:13px">Finding the live run…</p></div>`;
    try {
      const status = await API.pipelineStatus();
      if (status.status === 'running' && status.run_id) {
        const row = await API.get(`/papers/by-run/${status.run_id}`);
        location.hash = `papers/${row.id}`;
        return;
      }
    } catch (e) { /* fall through */ }
    container.innerHTML = `
      <div class="card" style="max-width:640px;margin:0 auto;text-align:center;padding:40px">
        <div style="font-size:36px;margin-bottom:10px">🌙</div>
        <p style="color:var(--text-secondary);margin-bottom:6px">Nothing is being written right now.</p>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:18px">Open a paper to see its full stage map, or start a new one.</p>
        <div style="display:flex;gap:10px;justify-content:center">
          <a href="#mypapers" class="g-btn" style="text-decoration:none">📚 My Papers</a>
          <a href="#newpaper" class="g-btn primary" style="text-decoration:none">✍️ New Paper</a>
        </div>
      </div>`;
  },
};
