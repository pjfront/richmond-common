// Parse a locator, never an attestation. deploy-prod.sh must still prove the
// returned host, project, approved SHA/ref and current alias via Vercels API.
// CLI59.1.4 deploy/index.js emits either getDeploymentOutputJson() or the
// nonInteractive {status: "ok", deployment: ...} envelope with --format=json.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const HOST = 'https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.vercel\\.app/?';
const URL_PATTERN = new RegExp(`^${HOST}$`);
const EDGE = '(?:[ \\t\\r]|\\x1b\\[(?:[0-9;]{0,32}m|2K|1G|G|\\?25[hl]))*';
const LABEL_GAP = '(?:[ \\t]|\\x1b\\[[0-9;]{0,32}m)+';
// Explicit single-line legacy forms only. Display codes can surround tokens;
// they cannot splice a URL together or hide another line/URL/OSC hyperlink.
const TEXT_PATTERN = new RegExp(`^${EDGE}(?:Production${LABEL_GAP})?(${HOST})${EDGE}\\n?$`);
const DEPLOYMENT_KEYS = new Set(['id', 'url', 'inspectorUrl', 'readyState', 'target', 'deploymentApiUrl']);
const ENVELOPE_KEYS = new Set(['status', 'deployment', 'message', 'next', 'hint']);
const LOCATOR_KEYS = new Set(['id', 'url', 'readyState', 'target', 'deployment', 'status', 'deploymentApiUrl']);
const ERROR_CODES = new Set(['output_bound', 'invalid_json', 'unexpected_json_shape', 'ambiguous_json_locator',
  'unexpected_json_envelope', 'invalid_json_deployment', 'unexpected_text_format']);

function fail(code) {
  throw new Error(code);
}

export function parseDeploymentOutput(input) {
  if (typeof input !== 'string' || Buffer.byteLength(input, 'utf8') > 16384) fail('output_bound');
  if (input.trimStart().startsWith('{') || input.trimStart().startsWith('[')) {
    let value;
    try { value = JSON.parse(input); } catch { fail('invalid_json'); }
    if (!value || Array.isArray(value) || typeof value !== 'object') fail('unexpected_json_shape');
    // JSON.parse alone silently accepts duplicate keys. Count decoded JSON key
    // tokens, including escaped spellings, before accepting a security field.
    const seen = new Set();
    for (const match of input.matchAll(/"(?:[^"\\]|\\.)*"\s*:/g)) {
      const key = JSON.parse(match[0].slice(0, match[0].lastIndexOf(':')).trimEnd());
      if (LOCATOR_KEYS.has(key) && seen.has(key)) fail('ambiguous_json_locator');
      seen.add(key);
    }
    let deployment = value;
    if (Object.hasOwn(value, 'deployment')) {
      if (value.status !== 'ok' || Object.keys(value).some(key => !ENVELOPE_KEYS.has(key))) fail('unexpected_json_envelope');
      deployment = value.deployment;
    }
    if (!deployment || Array.isArray(deployment) || typeof deployment !== 'object'
      || Object.keys(deployment).some(key => !DEPLOYMENT_KEYS.has(key))
      || !/^dpl_[A-Za-z0-9]+$/.test(deployment.id ?? '')
      || deployment.readyState !== 'READY' || deployment.target !== 'production'
      || typeof deployment.url !== 'string' || !URL_PATTERN.test(deployment.url)
      || (deployment.deploymentApiUrl !== undefined
        && deployment.deploymentApiUrl !== `https://api.vercel.com/v13/deployments/${deployment.id}`)) fail('invalid_json_deployment');
    return deployment.url.replace(/\/$/, '');
  }
  const match = input.match(TEXT_PATTERN);
  if (!match) fail('unexpected_text_format');
  return match[1].replace(/\/$/, '');
}

export function outputDiagnostic(input, code) {
  // Deliberately exclude raw stdout, unknown field names, URLs and messages:
  // npm notices/CLI errors could contain credentials or private source paths.
  return JSON.stringify({ code: ERROR_CODES.has(code) ? code : 'parser_error', bytes: Buffer.byteLength(input, 'utf8'),
    lines: input ? input.split('\n').length : 0, ansi: input.includes('\x1b'),
    format: input.trim() === '' ? 'empty' : /^[\s]*[\[{]/.test(input) ? 'json'
      : input.includes('Production') ? 'production_label' : input.startsWith('https://') ? 'bare_url' : 'other' });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const input = readFileSync(0, 'utf8');
  try { process.stdout.write(parseDeploymentOutput(input)); }
  catch (error) {
    process.stderr.write(`Deployment output diagnostic: ${outputDiagnostic(input, error.message)}\n`);
    process.exitCode = 2;
  }
}
