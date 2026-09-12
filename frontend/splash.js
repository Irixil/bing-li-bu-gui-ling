// Independent of app.js: opening the home page never waits for an API call.
(() => {
  const shell = document.querySelector('.app-shell');
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!shell) return;

  // The desktop iPhone canvas scrolls inside its frame.
  shell.addEventListener('click', event => {
    if (event.target.closest('[data-view]')) {
      shell.scrollTo({ top: 0, behavior: motion.matches ? 'instant' : 'smooth' });
    }
  });
  if (motion.matches) return;

  const overlay = document.createElement('section');
  overlay.className = 'web-splash';
  overlay.setAttribute('aria-label', '病历不归零，陪你记下来');
  // Clone the existing mark instead of introducing a new logo or palette.
  const mark = shell.querySelector('.brand-mark').cloneNode(true);
  mark.classList.add('web-splash__mark');
  mark.setAttribute('aria-hidden', 'true');
  overlay.append(mark);
  const title = document.createElement('h1');
  title.textContent = '病历不归零';
  const note = document.createElement('p');
  note.textContent = '陪你把每次不舒服记下来';
  const enter = document.createElement('button');
  enter.type = 'button';
  enter.className = 'web-splash__enter';
  enter.textContent = '进入首页';
  overlay.append(title, note, enter);
  document.body.append(overlay);

  let closed = false;
  let timer;
  let cleanupTimer;
  const wasInert = shell.inert;
  shell.inert = true;

  function cleanup() {
    clearTimeout(timer);
    clearTimeout(cleanupTimer);
    const hadFocus = overlay.contains(document.activeElement);
    shell.inert = wasInert;
    overlay.remove();
    motion.removeEventListener('change', onMotionChange);
    if (hadFocus) shell.querySelector('.quick-card')?.focus({ preventScroll: true });
  }
  function finish(immediate = false) {
    if (immediate) { closed = true; cleanup(); return; }
    if (closed) return;
    closed = true;
    clearTimeout(timer);
    overlay.classList.add('web-splash--leaving');
    cleanupTimer = setTimeout(cleanup, 550);
  }
  function onMotionChange(event) { if (event.matches) finish(true); }
  motion.addEventListener('change', onMotionChange);
  enter.addEventListener('click', () => finish());
  timer = setTimeout(finish, 2200);
  // On back/forward cache restoration, show the page immediately.
  window.addEventListener('pageshow', event => { if (event.persisted) finish(true); });
})();
