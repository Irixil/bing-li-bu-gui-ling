(() => {
  const screen = document.getElementById('splashScreen');
  const skip = document.getElementById('splashSkip');
  if (!screen || !skip) return;

  const key = 'elder_splash_seen_v1';
  const force = new URLSearchParams(location.search).get('splash') === '1';
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  let seen = false;
  try { seen = sessionStorage.getItem(key) === '1'; } catch {}

  function closeSplash() {
    if (screen.classList.contains('is-gone')) return;
    try { sessionStorage.setItem(key, '1'); } catch {}
    screen.classList.add('is-exiting');
    screen.setAttribute('aria-hidden', 'true');
    const finish = () => {
      screen.classList.add('is-gone');
      document.getElementById('homeTitle')?.focus({ preventScroll: true });
    };
    if (reducedMotion) finish();
    else setTimeout(finish, 300);
  }

  if (seen && !force) {
    screen.classList.add('is-gone');
    screen.setAttribute('aria-hidden', 'true');
    return;
  }

  skip.addEventListener('click', closeSplash);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeSplash();
  });
  setTimeout(closeSplash, reducedMotion ? 250 : 1700);
})();
