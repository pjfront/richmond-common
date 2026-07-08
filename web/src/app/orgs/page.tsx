/**
 * /orgs redirect — I164 split this into /unions and /corporations.
 */

import { redirect } from 'next/navigation'

export default function OrgsRedirect() {
  redirect('/unions')
}
