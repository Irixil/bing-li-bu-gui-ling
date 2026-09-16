const test = require('node:test');
const assert = require('node:assert/strict');

const { createConfig } = require('../frontend/config.js');

test('frontend port 5173 defaults to the independent backend port 18768', () => {
  const config = createConfig({ protocol: 'http:', hostname: '127.0.0.1', port: '5173', origin: 'http://127.0.0.1:5173' }, {});
  assert.equal(config.apiBaseUrl, 'http://127.0.0.1:18768');
  assert.equal(config.apiUrl('/api/app/session'), 'http://127.0.0.1:18768/api/app/session');
});

test('production frontend uses its explicit independent API address', () => {
  const config = createConfig(
    { protocol: 'https:', hostname: 'app.example.com', port: '', origin: 'https://app.example.com' },
    { apiBaseUrl: 'https://api.example.com/' },
  );
  assert.equal(config.apiBaseUrl, 'https://api.example.com');
  assert.equal(config.apiUrl('/health'), 'https://api.example.com/health');
});

test('unsafe API schemes are rejected and API paths must be absolute', () => {
  const config = createConfig(
    { protocol: 'https:', hostname: 'app.example.com', port: '', origin: 'https://app.example.com' },
    { apiBaseUrl: 'javascript:alert(1)' },
  );
  assert.equal(config.apiBaseUrl, '');
  assert.throws(() => config.apiUrl('api/app/session'), /api_path_must_start_with_slash/);
});
