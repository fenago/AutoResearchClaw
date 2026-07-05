/* Light / dark / system theme for the static site.
   Shares the localStorage "theme" key with the dashboard. */
(function () {
  function mode() { return localStorage.getItem('theme') || 'system'; }
  function apply() {
    var m = mode();
    var dark = m === 'dark' || (m === 'system' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  }
  apply();
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    if (mode() === 'system') apply();
  });

  document.addEventListener('DOMContentLoaded', function () {
    var nav = document.querySelector('.nav-links');
    if (!nav) return;
    var li = document.createElement('li');
    var sel = document.createElement('select');
    sel.title = 'Theme';
    sel.style.cssText = 'padding:4px 6px;font-size:0.8rem;background:var(--color-bg-alt);' +
      'color:var(--color-text);border:1px solid var(--color-border);border-radius:6px;cursor:pointer';
    [['system', '🖥 System'], ['dark', '🌙 Dark'], ['light', '☀️ Light']].forEach(function (o) {
      var opt = document.createElement('option');
      opt.value = o[0]; opt.textContent = o[1];
      sel.appendChild(opt);
    });
    sel.value = mode();
    sel.addEventListener('change', function () {
      localStorage.setItem('theme', sel.value);
      apply();
    });
    li.appendChild(sel);
    nav.appendChild(li);
  });
})();
