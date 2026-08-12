-- Migration 138: make public RPC execution an explicit allowlist.
-- Privilege-only forward migration. Do not apply without production approval.
-- Migration 134 remains untouched and forbidden.

-- Public read RPCs used by the frontend. Remove PostgreSQL's default PUBLIC
-- grant, then name the intended API roles explicitly.
REVOKE ALL PRIVILEGES ON FUNCTION public.find_similar_items(UUID, TEXT, INTEGER)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.find_similar_items(UUID, TEXT, INTEGER)
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.get_category_stats(TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_category_stats(TEXT)
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.get_contested_votes(TEXT, UUID[])
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_contested_votes(TEXT, UUID[])
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.get_controversial_items(TEXT, INTEGER)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_controversial_items(TEXT, INTEGER)
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.get_divergent_motions_detail(TEXT, UUID[])
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_divergent_motions_detail(TEXT, UUID[])
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.get_meeting_counts(TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_meeting_counts(TEXT)
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.get_meeting_flag_counts(TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_meeting_flag_counts(TEXT)
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.list_public_tables()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.list_public_tables()
  TO anon, authenticated, service_role;

-- Invoker-security get_category_stats calls this helper as the API role.
REVOKE ALL PRIVILEGES ON FUNCTION public.parse_vote_tally(TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.parse_vote_tally(TEXT)
  TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.search_hybrid(
  TEXT, extensions.vector, TEXT, TEXT, INTEGER, INTEGER
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.search_hybrid(
  TEXT, extensions.vector, TEXT, TEXT, INTEGER, INTEGER
) TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.search_site(
  TEXT, TEXT, TEXT, INTEGER, INTEGER
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.search_site(
  TEXT, TEXT, TEXT, INTEGER, INTEGER
) TO anon, authenticated, service_role;

-- Server/operator mutations. Repository callers use the service-role client.
REVOKE ALL PRIVILEGES ON FUNCTION public.check_and_increment_rate_limit(
  TEXT, INTEGER, INTEGER
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_and_increment_rate_limit(
  TEXT, INTEGER, INTEGER
) TO service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.cleanup_rate_limit_buckets()
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_rate_limit_buckets()
  TO service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.merge_official_pair(UUID, UUID)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.merge_official_pair(UUID, UUID)
  TO service_role;

-- Trigger functions need no direct API-role execution grant.
REVOKE ALL PRIVILEGES ON FUNCTION public.rls_auto_enable()
  FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.update_meeting_agenda_item_count()
  FROM PUBLIC, anon, authenticated, service_role;
