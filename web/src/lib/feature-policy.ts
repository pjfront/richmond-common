import policy from '@/data/feature-tiers.json'

export type FeatureProfile = keyof typeof policy.profiles
export type Feature = keyof typeof policy.features
export type Capability = keyof typeof policy.profiles.basic_public.capabilities

export function isLocalArchive(): boolean {
  // A cloud deployment must never gain the local archive's private surfaces.
  return process.env.RICHMOND_LOCAL_ARCHIVE === 'true' && !process.env.VERCEL
}

export function featureProfile(): FeatureProfile {
  const requested = process.env.RICHMOND_FEATURE_PROFILE
  const fallback = isLocalArchive() ? policy.defaults.local : policy.defaults.public
  const selected = requested?.trim() || fallback
  if (!Object.hasOwn(policy.profiles, selected)) return 'basic_public'
  if (selected.startsWith('local_') && !isLocalArchive()) return 'basic_public'
  return selected as FeatureProfile
}

export function featureEnabled(feature: Feature): boolean {
  return policy.profiles[featureProfile()].features[feature]
}

export function capabilityEnabled(capability: Capability): boolean {
  const profile = policy.profiles[featureProfile()]
  if (!profile.capabilities[capability]) return false
  if (['inference', 'embeddings', 'ocr'].includes(capability)) {
    if (!profile.allowPaid || isLocalArchive()) return false
    if (/^(1|true|yes|on)$/i.test(process.env.RICHMOND_API_BUDGET_LOCK?.trim() ?? '')) return false
    const cap = Number(process.env.RICHMOND_API_MONTHLY_CAP_USD ?? '0')
    if (!Number.isFinite(cap) || cap <= 0) return false
  }
  return true
}

function routeMatches(pattern: string, pathname: string): boolean {
  if (pattern.includes('*')) {
    const escaped = pattern.split('*').map(part => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[^/]+')
    return new RegExp(`^${escaped}$`).test(pathname)
  }
  // APIs are exact endpoints; a suffix must not borrow another route's rights.
  return pathname === pattern || (!pattern.startsWith('/api/') && pathname.startsWith(`${pattern}/`))
}

export function featureRouteAllowed(pathname: string, method: string): boolean {
  if (pathname === '/api/site-access' && method === 'POST') return true
  if (isLocalArchive() && ['/api/operator/login', '/api/operator/logout'].includes(pathname) && method === 'POST') return true
  if (method !== 'GET' && method !== 'HEAD') return false
  if (pathname === '/' || pathname === '/about' || pathname.startsWith('/about/') || pathname === '/elections/methodology') return true
  if (pathname.startsWith('/_next/static/') || pathname.startsWith('/_next/webpack-hmr')) return true
  if (['/favicon.ico', '/icon.svg', '/apple-icon', '/robots.txt', '/sitemap.xml'].includes(pathname)) return true
  if (isLocalArchive() && (pathname === '/library' || pathname.startsWith('/data/'))) return true
  const candidates: Array<{ feature: Feature; pattern: string }> = []
  for (const [id, feature] of Object.entries(policy.features)) {
    const patterns = [...feature.routes, ...(isLocalArchive() && 'localRoutes' in feature ? feature.localRoutes : [])]
    for (const pattern of patterns) {
      if (routeMatches(pattern, pathname)) candidates.push({ feature: id as Feature, pattern })
    }
  }
  candidates.sort((a, b) => b.pattern.length - a.pattern.length)
  return Boolean(candidates.length && featureEnabled(candidates[0].feature))
}

export function localRequestAllowed(url: URL, headers: Headers): boolean {
  const loopback = (hostname: string) => ['127.0.0.1', 'localhost', '[::1]'].includes(hostname.toLowerCase())
  if (!loopback(url.hostname)) return false
  for (const name of ['host', 'x-forwarded-host']) {
    const value = headers.get(name)
    if (!value) continue
    try {
      const host = new URL(`http://${value}`)
      // Next normalizes 127.0.0.1 to localhost internally. Require loopback
      // and the same port instead of trusting a literal hostname alias.
      if (!loopback(host.hostname) || host.port !== url.port) return false
    } catch { return false }
  }
  const origin = headers.get('origin')
  if (!origin) return true
  try {
    const source = new URL(origin)
    return loopback(source.hostname) && source.port === url.port && source.protocol === url.protocol && origin === source.origin
  } catch { return false }
}

export const featureCatalog = policy.features
