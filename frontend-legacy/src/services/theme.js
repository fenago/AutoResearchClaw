/**
 * Theme — light / dark / system preference. Applied immediately on load
 * (include this script in <head>) to avoid a flash of the wrong theme.
 */
const Theme = {
  get() {
    return localStorage.getItem('theme') || 'system';
  },

  set(mode) {
    localStorage.setItem('theme', mode);
    this.apply();
  },

  apply() {
    const mode = this.get();
    const dark = mode === 'dark'
      || (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  },
};

Theme.apply();
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (Theme.get() === 'system') Theme.apply();
});
