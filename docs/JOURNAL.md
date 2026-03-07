# Project Journal — Richmond Transparency Project

*Narrative chronicle of the project's arc, decisions, mistakes, and growth. Each entry has a narrative section followed by a "serious stuff" technical appendix.*

---

## 2026-03-06: The System Gets Eyes

The pipeline learned to see itself today.

For months, the Richmond Transparency Project has been a machine that runs when triggered and stays silent about its own health. Fifteen items scraped? Great. Three items scraped from a meeting that usually has twenty? Also great, as far as the pipeline knew. It did its work, wrote its output, and waited for a human to notice when something went wrong.

That changes with Phase A of the autonomy zones. Not with self-modification. Not with autonomous decision-making. Just observation. The pipeline now writes a structured journal entry after every step: what happened, how many items, how long it took. If the count deviates from recent history by more than 50%, it flags the anomaly. If a step takes three times longer than usual, it notes that too. After every run, Claude Sonnet reads the recent journal and produces a health assessment. A decision packet for the operator.

The philosophy is simple: you can't heal what you can't see. Phase A gives the system eyes before it gets hands.

The design was deliberately conservative. Every journal write is wrapped in try/except. If the journal table doesn't exist, the pipeline runs identically to before. The anomaly detector requires three data points of history before it will flag anything, avoiding false positives during initial deployment. The self-assessment costs about $0.016 per call, running maybe twice a week. The system observes but does not act.

This is the foundation for everything that comes next: self-healing scrapers, autonomous config updates, graduated trust in the system's own judgment. But foundations are boring on purpose. You want the exciting stuff to stand on something solid.

### Serious Stuff

**What shipped:**
- `pipeline_journal` table (migration 015): append-only, UUID-keyed, JSONB metrics, partial indexes for hot query paths
- `PipelineJournal` class: non-fatal journal writer with `log_step`, `log_anomaly`, `log_run_start/end`, `log_assessment`
- Anomaly detection: `detect_count_anomaly` (threshold-based, configurable) and `detect_timing_anomaly` (multiplier-based)
- `check_anomalies` convenience wrapper: queries history + runs both detectors
- `self_assessment.py`: context builder, LLM runner (Sonnet), decision packet formatter, CLI
- Full instrumentation of `cloud_pipeline.py` (10 steps + run lifecycle) and `data_sync.py` (run lifecycle)
- 41 new tests (28 journal + 13 self-assessment), 897 total, all passing
- GitHub Actions: per-run assessment in cloud-pipeline.yml and data-sync.yml, daily digest cron in self-assessment.yml
- `staleness_monitor.py` updated with new table

**Files created:** 7 (migration, pipeline_journal.py, self_assessment.py, 2 prompts, 2 test files, 1 workflow)
**Files modified:** 5 (db.py, cloud_pipeline.py, data_sync.py, staleness_monitor.py, 2 existing workflows)

**Phase A scope boundary:** observation only. No free zone, no proposal zone, no self-modification. That's Phase B.

**Operator action required:** Run `src/migrations/015_pipeline_journal.sql` in [Supabase SQL Editor](https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/).
