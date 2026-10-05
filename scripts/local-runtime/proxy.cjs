// Loopback-only Supabase /rest/v1 compatibility proxy. No model/email/cloud API.
const http = require('node:http');
const fs = require('node:fs');

function routeAllowed(method, pathname, readRpcs) {
  if (!pathname.startsWith('/rest/v1/')) return false;
  const path = pathname.slice('/rest/v1/'.length);
  if (/^[a-z][a-z0-9_]*$/.test(path)) return ['GET', 'HEAD', 'OPTIONS'].includes(method);
  const rpc = /^rpc\/([a-z][a-z0-9_]*)$/.exec(path);
  return Boolean(rpc && readRpcs.includes(rpc[1]) && ['GET', 'HEAD', 'POST', 'OPTIONS'].includes(method));
}

function start(config) {
  if (config.host !== '127.0.0.1' || config.upstreamHost !== '127.0.0.1') throw new Error('Loopback-only configuration required');
  const origins = new Set([`http://127.0.0.1:${config.webPort}`, `http://localhost:${config.webPort}`]);
  const hosts = new Set([`127.0.0.1:${config.port}`, `localhost:${config.port}`]);
  const server = http.createServer((request, response) => {
    response.setHeader('Cache-Control', 'private, no-store');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    const deny = (status) => { response.writeHead(status, { 'Content-Type': 'application/json' }); response.end(JSON.stringify({ error: 'Unavailable in the local read-only archive' })); };
    if (!request.url.startsWith('/') || request.url.startsWith('//')) { deny(403); return; }
    let url;
    try { url = new URL(request.url, `http://127.0.0.1:${config.port}`); } catch { deny(400); return; }
    if (!hosts.has(request.headers.host) || (request.headers.origin && !origins.has(request.headers.origin)) || !routeAllowed(request.method, url.pathname, config.readRpcs)) { deny(403); return; }
    if (request.headers.origin) {
      response.setHeader('Access-Control-Allow-Origin', request.headers.origin);
      response.setHeader('Vary', 'Origin');
    }
    if (request.method === 'OPTIONS') {
      response.writeHead(204, { 'Access-Control-Allow-Methods': 'GET, HEAD, POST, OPTIONS', 'Access-Control-Allow-Headers': 'authorization,apikey,content-type,accept,prefer,range,range-unit,x-client-info,accept-profile,content-profile', 'Access-Control-Expose-Headers': 'Content-Range,Content-Type' });
      response.end(); return;
    }
    const headers = {};
    for (const name of ['authorization', 'apikey', 'content-type', 'accept', 'prefer', 'range', 'range-unit', 'x-client-info', 'accept-profile', 'content-profile']) {
      if (request.headers[name]) headers[name] = request.headers[name];
    }
    const chunks = []; let size = 0;
    request.on('data', chunk => { size += chunk.length; if (size > 8192) { deny(413); request.destroy(); } else chunks.push(chunk); });
    request.on('end', () => {
      if (response.writableEnded) return;
      const upstream = http.request({ host: '127.0.0.1', port: config.upstreamPort, path: url.pathname.slice('/rest/v1'.length) + url.search, method: request.method, headers, timeout: 15000 }, result => {
        for (const name of ['content-type', 'content-range', 'range-unit', 'preference-applied']) {
          if (result.headers[name]) response.setHeader(name, result.headers[name]);
        }
        response.writeHead(result.statusCode ?? 502); result.pipe(response);
      });
      upstream.on('timeout', () => upstream.destroy());
      upstream.on('error', () => { if (!response.headersSent) deny(503); else response.destroy(); });
      upstream.end(Buffer.concat(chunks));
    });
  });
  server.listen(config.port, '127.0.0.1');
  return server;
}

if (require.main === module) start(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
module.exports = { routeAllowed, start };
