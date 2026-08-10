import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/operator/', '/subscribe/manage'],
      },
    ],
    sitemap: 'https://richmondcommons.org/sitemap.xml',
  }
}
