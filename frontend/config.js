(function (root, factory) {
  'use strict';
  const createConfig = factory();
  root.BingliConfig = createConfig(root.location, root.__BINGLI_CONFIG__);
  if (typeof module !== 'undefined' && module.exports) module.exports = { createConfig };
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function createConfig(locationLike = {}, injected = {}) {
    const hostname = String(locationLike.hostname || '');
    const protocol = String(locationLike.protocol || 'http:');
    const port = String(locationLike.port || '');
    const isLocalFrontend = ['127.0.0.1', 'localhost'].includes(hostname) && port === '5173';
    const explicit = typeof injected?.apiBaseUrl === 'string' ? injected.apiBaseUrl.trim() : '';
    const candidate = explicit || (isLocalFrontend ? `${protocol}//${hostname}:18768` : '');
    let apiBaseUrl = '';
    if (candidate) {
      try {
        const parsed = new URL(candidate, locationLike.origin || undefined);
        if (['http:', 'https:'].includes(parsed.protocol)) apiBaseUrl = parsed.href.replace(/\/$/, '');
      } catch {}
    }
    return Object.freeze({
      apiBaseUrl,
      apiUrl(path) {
        const suffix = String(path || '');
        if (!suffix.startsWith('/')) throw new TypeError('api_path_must_start_with_slash');
        return `${apiBaseUrl}${suffix}`;
      },
    });
  }

  return createConfig;
});
