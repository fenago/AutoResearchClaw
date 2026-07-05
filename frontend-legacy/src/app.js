/**
 * ResearchClaw SPA — main application entry point.
 */
(function () {
  'use strict';

  // View registry
  const views = {
    newpaper: NewPaper,
    mypapers: MyPapers,
    progress: ProgressView,
    dashboard: Dashboard,
    pipeline: PipelineView,
    chat: ChatPanel,
    experiments: ExperimentMonitor,
    paper: PaperPreview,
    projects: ProjectList,
    wizard: WizardFlow,
    llm: LLMSettings,
    users: UserAdmin,
    account: Account,
  };

  let currentView = 'newpaper';

  function navigateTo(viewName) {
    if (!views[viewName]) return;
    currentView = viewName;
    if (location.hash.slice(1).split('/')[0] !== viewName) {
      history.replaceState(null, '', '#' + viewName);
    }

    // Update nav
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.view === viewName);
    });

    // Render view
    const main = document.getElementById('main-content');
    if (main) {
      const view = views[viewName];
      if (view.render) {
        view.render(main);
      }
    }
  }

  // Init
  document.addEventListener('DOMContentLoaded', async () => {
    // Theme selector
    const themeSel = document.getElementById('theme-select');
    if (themeSel) {
      themeSel.value = Theme.get();
      themeSel.addEventListener('change', () => Theme.set(themeSel.value));
    }

    // Auth gate — stops here (login overlay shown) until signed in
    const authed = await Auth.init();
    if (!authed) return;

    // Bind navigation
    document.querySelectorAll('.nav-item[data-view]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        navigateTo(el.dataset.view);
      });
    });

    // Connect events WebSocket
    eventsWS.on('open', () => {
      const badge = document.getElementById('connection-badge');
      if (badge) {
        badge.textContent = 'Connected';
        badge.className = 'status-badge running';
      }
    });

    eventsWS.on('close', () => {
      const badge = document.getElementById('connection-badge');
      if (badge) {
        badge.textContent = 'Disconnected';
        badge.className = 'status-badge failed';
      }
    });

    // Route events to active view
    eventsWS.on('message', (data) => {
      const view = views[currentView];
      if (view && view.onEvent) {
        view.onEvent(data);
      }

      // Browser notifications
      if (Notification.permission === 'granted') {
        if (data.type === 'pipeline_completed') {
          new Notification('ResearchClaw', { body: 'Pipeline completed!' });
        } else if (data.type === 'stage_fail') {
          new Notification('ResearchClaw', { body: `Stage failed: ${data.data?.current_stage_name || ''}` });
        }
      }
    });

    eventsWS.connect();

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    // Hash routing (#view or #papers/<id>)
    function applyHash() {
      const h = location.hash.slice(1);
      if (h.startsWith('papers/')) {
        MyPapers._pendingId = h.split('/')[1];
        navigateTo('mypapers');
        return;
      }
      navigateTo(views[h] ? h : 'newpaper');
    }
    window.addEventListener('hashchange', applyHash);
    applyHash();

    // Update header status
    try {
      const health = await API.health();
      const statusEl = document.getElementById('server-status');
      if (statusEl) statusEl.textContent = `v${health.version}`;
    } catch (e) {
      console.warn('Health check failed:', e);
    }

    // Honest live sidebar entry: shows the paper being written right now, with
    // live percent, linking straight to it. Appears only when a run is active.
    async function refreshLiveNav() {
      try {
        const status = await API.pipelineStatus();
        let el = document.getElementById('live-run-nav');
        if (status.status === 'running' && status.run_id) {
          const pct = (status.progress && status.progress.percent) || 0;
          const title = status.title || 'your paper';
          const waiting = status.waiting ? ' · needs you' : '';
          if (!el) {
            const nav = document.querySelector('.sidebar');
            if (nav) {
              const box = document.createElement('div');
              box.className = 'sidebar-section';
              box.id = 'live-run-section';
              box.innerHTML = `<h3>Live</h3><a class="nav-item" id="live-run-nav" href="#"></a>`;
              nav.insertBefore(box, nav.firstChild);
              el = document.getElementById('live-run-nav');
            }
          }
          if (el) {
            el.innerHTML = `<span class="live-dot"></span> <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${title}</span> <span style="font-size:11px;color:var(--accent)">${pct}%${waiting}</span>`;
            el.onclick = async (e) => {
              e.preventDefault();
              try { const row = await API.get(`/papers/by-run/${status.run_id}`); location.hash = `papers/${row.id}`; } catch (_) {}
            };
          }
        } else {
          const sec = document.getElementById('live-run-section');
          if (sec) sec.remove();
        }
      } catch (e) { /* ignore */ }
    }
    refreshLiveNav();
    setInterval(refreshLiveNav, 7000);
  });
})();
