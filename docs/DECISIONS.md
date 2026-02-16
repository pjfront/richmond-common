# Decisions Log — Richmond Transparency Project

*Record key decisions and rationale so future-you doesn't wonder "why did I do it this way?"*

---

## 2025-02-15: Use FIPS codes for city disambiguation from day one
**Decision:** Every record includes `city_fips` (e.g., Richmond CA = 0660620, Richmond VA = 5167000). Every web search includes "Richmond, California" not just "Richmond."
**Rationale:** Cheap to implement now, catastrophically expensive to retrofit at city #50. Prevents data corruption when scaling horizontally.

## 2025-02-15: PostgreSQL + pgvector, no separate vector DB
**Decision:** Use pgvector extension in PostgreSQL for embeddings instead of Pinecone/Weaviate/etc.
**Rationale:** Single query can combine vector similarity with SQL filtering. One database to manage. Good enough performance for our scale. Reduces infrastructure complexity and cost.

## 2025-02-15: Three-layer database architecture
**Decision:** Document Lake (raw, flexible) → Structured Core (normalized, fast) → Embedding Index (semantic search).
**Rationale:** Preserves raw data for re-extraction as prompts improve. Structured layer enables fast cross-referencing (the conflict scanner needs JOINs, not embeddings). Embedding layer handles natural language search.

## 2025-02-15: "Sunlight not surveillance" positioning
**Decision:** Frame as governance assistant that helps cities work better, not adversarial watchdog tool.
**Rationale:** Phillip's Personnel Board seat requires collaborative framing. City staff adoption more likely if not perceived as hostile. Accountability is natural consequence of transparency — doesn't need to be the pitch.

## 2025-02-15: Don't file entity yet
**Decision:** Build prototype as individual. Fiscal sponsorship + LLC later.
**Rationale:** Entity structure depends on traction — startup path (C-corp/PBC), mission path (501c3), or both (Mozilla model). Filing prematurely locks in structure before data informs the choice.

## 2025-02-15: Four-tier source credibility hierarchy
**Decision:** Tier 1 (official records) > Tier 2 (independent journalism) > Tier 3 (stakeholder comms, disclosed bias) > Tier 4 (community/social, context only).
**Rationale:** RAG retrieval must weight sources appropriately. Richmond Standard (Chevron-funded) can't have same weight as certified council minutes. Tom Butt's blog is invaluable context but not neutral fact. Always disclose bias.

## 2025-02-15: Free for Richmond, revenue from scaling
**Decision:** Richmond pilot is free. Revenue comes from other cities, professional tiers, and grants.
**Rationale:** Real deployment validates product. Richmond becomes the case study. 280 subscribers at $5/month covers all Richmond costs (0.24% of population) if self-sustaining model needed later.
