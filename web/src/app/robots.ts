import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
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
