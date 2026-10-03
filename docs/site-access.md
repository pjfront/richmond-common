# Temporary site password protection

The October 3, 2026 operator instruction authorizes a temporary password gate while Richmond Commons is redesigned around agenda items, tags, recorded votes, campaign donations and natural-language search. This gate is application code and requires no paid hosting protection feature.

## Configuration

Set `SITE_ACCESS_REQUIRED=true` and a high-entropy server-only `SITE_ACCESS_PASSWORD` of at least 24 characters in the Production environment. These variables must never have a `NEXT_PUBLIC_` prefix, appear in URLs or logs, or be committed with secret values. The isolated-preview build guard rejects `SITE_ACCESS_PASSWORD` so a production credential cannot leak into preview scope.

The visible entry page is a self-contained password form served by middleware. It has no username, account registration, access-request link or external resources. It posts only to `/api/site-access`, which requires a same-origin form submission, validates the password, seals a separate `rtp_site_access` cookie and redirects with HTTP 303 to a safe local return path. The cookie lasts seven days, uses HttpOnly and SameSite strict, is Secure in production, and grants no operator privileges. Its sealing key is derived from the password with a separate SHA-256 namespace; rotating the password invalidates existing site cookies without changing operator sessions. The existing operator sign-in remains separate.

Only the explicit `true` flag enables the gate. Local builds and isolated previews retain their existing behavior without this flag. When enabled, a missing or invalid password configuration returns HTTP 503, including health and job routes. It never reopens public access. Disable the flag deliberately when the redesigned site is ready for public release.

## Protected surface

Middleware matches every route, including root, meeting and item pages, RSC/prefetch requests, search/export APIs, assets, the image optimizer, metadata routes and files with extensions. There is no blanket exception for `/api`, `/_next`, robots, sitemap or file types. Access responses and authenticated responses carry `private, no-store`, CDN no-store and `noindex, nofollow` headers during the hold. Authorization headers and passwords are not logged.

Credential checks compare fixed-size SHA-256 digests with Web Crypto. No database or paid service is called to authenticate site access. Basic authorization remains supported for bounded scripted verification, but the gate never sends `WWW-Authenticate` and never triggers a browser-native authentication popup.

## Narrow service exceptions

The following exceptions preserve existing independent authorization. A machine secret never provides general browsing access, and allowing a request through middleware does not bypass the route's own checks.

| Route | Method | Credential |
| --- | --- | --- |
| `/api/site-access` | POST | Same-origin password form; sets only the site cookie |
| `/api/email/send-recap` | POST | Bearer `API_SECRET` |
| `/api/email/send-orientation` | POST | Bearer `API_SECRET` |
| `/api/email/retry-deliveries` | POST | Bearer `API_SECRET` |
| `/api/email/send-digest` | GET, POST | Bearer `API_SECRET` |
| `/api/health` | GET | Bearer `API_SECRET`, site cookie, or scripted Basic access |
| `/api/revalidate` | POST | JSON `secret` matching configured `REVALIDATION_SECRET` |
| `/api/subscribe?token=...` | GET | Existing subscriber-token validation |

Revalidation authentication reads a clone bounded to 8 KiB, leaving the original job body intact. The route also enforces this bound and refuses missing `REVALIDATION_SECRET`; forwarded addresses cannot substitute for a credential. Existing tokenized unsubscribe links remain usable and return self-contained confirmation HTML. Signup and preference-management pages remain behind site access during the hold.

Anonymous `GET /api/health` returns only `{"status":"protected"}` without reading the database or exposing schema/source details. Authorized callers still reach the existing real health handler. The public alerting probe recognizes the Richmond Commons HTTP 401 form response with `X-Richmond-Site-Access: required` and the synthetic protected health response as an intentional hold. An arbitrary 401 or disagreement between root and health still fails monitoring. A protected result establishes gate availability, not database health.

## Verification and release

Before relaxing temporary hosting protection, verify the deployed application returns its own password form anonymously on root and direct item paths, with no external redirect or native authentication popup. Verify search/export APIs, RSC/prefetch requests and a real static asset remain protected. Submit the password form with its same-origin header, verify the HttpOnly cookie opens the requested page, and verify wrong passwords and unsafe origins/return paths fail. Verify anonymous health contains only the protected status, authenticated health still works, and the existing service exceptions retain their methods and credential checks. Never put passwords in verification URLs or output.

Use the existing exact-source production deploy process. This document does not attest a deployment or change provider settings. The gate limits website access; it does not revoke access to city source portals, previously downloaded material or intentionally public database projections.
