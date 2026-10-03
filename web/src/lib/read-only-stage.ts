/** Private relaunch previews may read public records, but never mutate them. */
export function isReadOnlyStage(): boolean {
  return process.env.RICHMOND_READ_ONLY_STAGE === 'true'
}

export function stageRouteAllowed(pathname: string, method: string): boolean {
  // This endpoint changes only the browser's access cookie; it cannot write
  // civic records and independently checks the password and request origin.
  if (pathname === '/api/site-access' && method === 'POST') return true
  if (method !== 'GET' && method !== 'HEAD') return false
  if (pathname.startsWith('/api/')) return ['/api/commons/search', '/api/finance/export'].includes(pathname)
  if (pathname === '/' || pathname === '/search' || pathname === '/money') return true
  if (pathname === '/meetings' || pathname.startsWith('/meetings/')) return true
  if (pathname === '/about' || pathname.startsWith('/about/')) return true
  if (pathname === '/elections/methodology') return true
  if (pathname.startsWith('/_next/static/')) return true
  return ['/favicon.ico', '/icon.svg', '/apple-icon', '/robots.txt', '/sitemap.xml'].includes(pathname)
}
