-- Migration 041: Widen nextrequest_requests.department to TEXT
-- NextRequest API returns comma-separated department lists that can exceed 200 chars.
-- Idempotent: ALTER TYPE to TEXT is a no-op if already TEXT.

ALTER TABLE nextrequest_requests
  ALTER COLUMN department TYPE TEXT;
