import type { MetadataRoute } from 'next'
import { isReadOnlyStage } from '@/lib/read-only-stage'

export default function robots(): MetadataRoute.Robots {
  if (isReadOnlyStage()) return { rules: { userAgent: '*', disallow: '/' } }
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/operator/'],
      },
      {
        userAgent: 'Amazonbot',
        allow: '/',
        disallow: ['/api/', '/operator/', '/meetings/*/items/'],
      },
    ],
    sitemap: 'https://richmondcommons.org/sitemap.xml',
  }
}
