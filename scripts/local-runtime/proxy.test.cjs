const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { start } = require('./proxy.cjs');

function listen(server) { return new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); }
function request(port, path, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, path, method: options.method ?? 'GET', headers: options.headers ?? {} }, response => {
      let body = ''; response.on('data', chunk => { body += chunk; });
      response.on('end', () => resolve({ status: response.statusCode, headers: response.headers, body }));
    });
    req.on('error', reject); req.end(options.body ?? '');
  });
}

test('localhost proxy forwards a public read/RPC while denying write, foreign-origin, and arbitrary-target requests', async () => {
  const seen = [];
  const upstream = http.createServer((req, res) => {
    seen.push({ path: req.url, method: req.method });
    res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Range': '0-0/1' }); res.end('[{"id":"test-public-id"}]');
  });
  await listen(upstream);
  const proxy = start({ host: '127.0.0.1', port: 0, upstreamHost: '127.0.0.1', upstreamPort: upstream.address().port, webPort: 3100, readRpcs: ['search_site'] });
  await new Promise(resolve => proxy.on('listening', resolve));
  const port = proxy.address().port;
  // This test assigns an ephemeral listener, while production validates its fixed configured port.
  const headers = { Host: '127.0.0.1:0', Origin: 'http://127.0.0.1:3100' };
  try {
    const read = await request(port, '/rest/v1/meetings?select=id', { headers });
    assert.equal(read.status, 200); assert.equal(read.headers['content-range'], '0-0/1');
    assert.equal(read.headers['cache-control'], 'private, no-store');
    const rpc = await request(port, '/rest/v1/rpc/search_site', { method: 'POST', headers, body: '{"p_query":"housing"}' });
    assert.equal(rpc.status, 200);
    for (const [path, method, extra] of [
      ['/rest/v1/meetings', 'POST', {}], ['/rest/v1/meetings', 'DELETE', {}],
      ['/rest/v1/rpc/review_decision', 'POST', {}], ['/auth/v1/token', 'POST', {}],
      ['/rest/v1/meetings', 'GET', { Origin: 'https://unrelated.example' }],
      ['/rest/v1/meetings', 'GET', { Host: 'unrelated.example' }],
      ['http://unrelated.example/rest/v1/meetings', 'GET', {}],
      ['/rest/v1/../config/secrets.json', 'GET', {}],
    ]) {
      const response = await request(port, path, { method, headers: { ...headers, ...extra } });
      assert.equal(response.status, 403, `${method} ${path}`);
    }
    assert.deepEqual(seen, [{ path: '/meetings?select=id', method: 'GET' }, { path: '/rpc/search_site', method: 'POST' }]);
  } finally { await new Promise(resolve => proxy.close(resolve)); await new Promise(resolve => upstream.close(resolve)); }
});
