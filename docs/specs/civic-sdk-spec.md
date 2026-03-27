# Civic Transparency SDK — Architecture Specification

**Version:** 0.1.0-draft
**Author:** Project operator (spec) + Claude (drafting partner)
**Audience:** Claude Code (primary implementer)
**Status:** Ready for review → then implementation

---

## 1. What This Is

The Civic Transparency SDK (`civic_sdk`) is a Python package that encodes the non-negotiable conventions of Richmond Commons into reusable, enforceable code. It is the foundation that all pipeline code, extraction logic, and future application layers build on top of.

### Why It Exists

Today, conventions like "every record needs a FIPS code" and "every source needs a credibility tier" are enforced by humans remembering to follow them. The SDK makes the computer enforce them instead. If code tries to store a record without a FIPS code, it fails. If code tries to ingest a document without a source tier, it fails. **Decide once, enforce always.**

### Design Philosophy

- **Convention violations are errors, not warnings.** The SDK raises exceptions when rules are broken, not log messages that get ignored.
- **Single-city works standalone.** A developer should be able to use this SDK for one city without needing any multi-city orchestration. Multi-city is a layer that sits on top (Layers 4-5, not part of this package).
- **Open-core boundary.** Layers 1-3 (convention enforcement, pipeline primitives, entity resolution) are designed to be open-sourced. Layers 4-5 (multi-city orchestration, spec/configuration intelligence) are proprietary and live in a separate private repo that imports this SDK. **Nothing in this package should assume or require the proprietary layers.**
- **Instrumentation before optimization.** Every convention enforcement point should log what it enforced and why, so we can measure how often rules catch mistakes before we tune anything.

---

## 2. Package Structure

```
civic_sdk/
├── __init__.py              # Public API exports
├── conventions/
│   ├── __init__.py
│   ├── fips.py              # FIPS code validation and enforcement
│   ├── tiers.py             # Source credibility tier system
│   ├── disclosure.py        # Bias and AI disclosure requirements
│   └── identifiers.py       # Universal identifier generation
├── db/
│   ├── __init__.py
│   ├── connection.py        # Database connection management
│   ├── document_lake.py     # Layer 1: raw document storage
│   ├── structured_core.py   # Layer 2: normalized tables
│   ├── embedding_index.py   # Layer 3: pgvector operations
│   └── schema.py            # Schema definitions and migrations
├── models/
│   ├── __init__.py
│   ├── base.py              # Base model with enforced fields
│   ├── city.py              # City configuration model
│   ├── official.py          # Elected/appointed official model
│   ├── meeting.py           # Meeting, agenda item, vote models
│   ├── document.py          # Document lake record model
│   └── contribution.py      # Campaign finance models
├── exceptions.py            # Custom exception hierarchy
├── logging.py               # Structured logging with enforcement tracking
└── config.py                # SDK configuration (DB URLs, API keys, etc.)
```

### What Lives Where

| Directory | Purpose | Layer |
|-----------|---------|-------|
| `conventions/` | Rules that apply everywhere — FIPS, tiers, disclosure | 1 |
| `db/` | Database access that enforces the three-layer pattern | 1 (foundation for 2) |
| `models/` | Data models with built-in validation | 1 (foundation for 2) |

Layer 2 (pipeline primitives like `Source`, `Extraction`, `Pipeline`) and Layer 3 (entity resolution) will be added as new top-level directories (`civic_sdk/sources/`, `civic_sdk/extraction/`, `civic_sdk/entities/`) in future phases. The Layer 1 code must not block or complicate their addition.

---

## 3. Module Specifications

### 3.1 `conventions/fips.py` — FIPS Code Enforcement

FIPS codes are the universal city identifier. There are 27 Richmonds in the US. Every record in every table must be attributable to a specific city.

```python
# Public API

def validate_fips(code: str) -> str:
    """
    Validate a FIPS code format and return the normalized form.
    
    FIPS place codes are 7 digits: 2-digit state + 5-digit place.
    Raises InvalidFIPSError if format is wrong.
    Does NOT validate against a lookup table (that's Layer 4 territory —
    we don't want to bundle a 19K-city database in the open-source SDK).
    
    Args:
        code: Raw FIPS code string (e.g., "0660620", "660620")
    
    Returns:
        Normalized 7-digit string, zero-padded (e.g., "0660620")
    
    Raises:
        InvalidFIPSError: If code cannot be normalized to valid format
    """

def require_fips(func):
    """
    Decorator that enforces city_fips is present and valid in function kwargs
    or in the first positional argument (if it's a dict or model instance).
    
    Usage:
        @require_fips
        def store_meeting(meeting_data: dict) -> None:
            ...
    
    Raises:
        MissingFIPSError: If city_fips is not present
        InvalidFIPSError: If city_fips format is invalid
    """

class FIPSMixin:
    """
    Mixin for data models that require a FIPS code.
    Adds city_fips field with automatic validation on assignment.
    All models in civic_sdk/models/ must inherit from this.
    """
    city_fips: str  # Validated on set
```

**Key decisions:**
- Format validation only, not existence validation. We validate that "0660620" *looks like* a FIPS code, but we don't ship a database of all valid FIPS codes. That's a multi-city concern (Layer 4). A single-city user just needs to know their own FIPS code.
- Zero-padding is automatic. "660620" becomes "0660620".
- The decorator pattern lets us enforce FIPS on any function without modifying its internals.

### 3.2 `conventions/tiers.py` — Source Credibility Tiers

Every piece of ingested content must be tagged with its credibility tier. This affects how downstream features weight and present the information.

```python
from enum import IntEnum

class SourceTier(IntEnum):
    """
    Source credibility tiers. Higher number = lower credibility.
    IntEnum so tiers can be compared: SourceTier.OFFICIAL < SourceTier.COMMUNITY
    """
    OFFICIAL = 1       # Government records: certified minutes, resolutions, CAL-ACCESS, budgets
    JOURNALISM = 2     # Independent journalism: Richmond Confidential, East Bay Times, KQED
    STAKEHOLDER = 3    # Stakeholder comms: Tom Butt E-Forum, Richmond Standard (Chevron-funded)
    COMMUNITY = 4      # Community/social: Nextdoor, public comments, social media


def require_tier(func):
    """
    Decorator that enforces source_tier is present and is a valid SourceTier.
    
    Raises:
        MissingTierError: If source_tier is not present
        InvalidTierError: If source_tier is not a valid SourceTier value
    """


class TierMixin:
    """
    Mixin for data models that require a source tier.
    Adds source_tier field with automatic validation.
    """
    source_tier: SourceTier


# Tier-specific metadata requirements
TIER_REQUIREMENTS: dict[SourceTier, list[str]] = {
    SourceTier.OFFICIAL: [],  # No additional metadata required
    SourceTier.JOURNALISM: ["outlet_name"],
    SourceTier.STAKEHOLDER: ["outlet_name", "disclosure_note"],  # disclosure_note is MANDATORY
    SourceTier.COMMUNITY: ["platform_name"],
}


def validate_tier_metadata(tier: SourceTier, metadata: dict) -> None:
    """
    Validate that required metadata fields are present for the given tier.
    
    For Tier 3 (STAKEHOLDER), disclosure_note is mandatory. This is where
    we enforce rules like "Richmond Standard must always disclose Chevron funding."
    
    Raises:
        MissingTierMetadataError: If required fields are absent
    """
```

**Key decisions:**
- `IntEnum` so tiers are comparable. This matters for retrieval: "only show me Tier 1-2 sources" becomes a simple `<=` comparison.
- Tier 3 *requires* a disclosure note. You cannot store a Tier 3 source without explaining the bias. The SDK literally won't let you.
- Tier-specific metadata requirements are defined in one place. When Layer 2 builds the ingestion pipeline, it checks these requirements automatically.

### 3.3 `conventions/disclosure.py` — Bias and AI Disclosure

Two types of mandatory disclosure: source bias and AI-generated content.

```python
# Known sources with mandatory disclosure text
# This registry is the single source of truth for bias disclosures.
# When a source is ingested, the SDK checks this registry and attaches
# the disclosure automatically.

MANDATORY_DISCLOSURES: dict[str, str] = {
    "richmond_standard": "The Richmond Standard is funded by Chevron Richmond.",
    "tom_butt_eforum": "Tom Butt's E-Forum is a personal newsletter by a sitting council member.",
    # Extensible: new entries added as sources are onboarded
}


def get_disclosure(source_key: str) -> str | None:
    """Return mandatory disclosure text for a known source, or None."""


def require_ai_disclosure(content: str) -> str:
    """
    Prepend AI disclosure to any AI-generated content that will be
    sent to humans (e.g., plain-language summaries, public comments).
    
    Returns:
        Content with disclosure prepended.
    
    Note:
        Internal pipeline content (embeddings, intermediate extractions)
        does NOT need this disclosure. Only human-facing output.
    """

AI_DISCLOSURE_PREFIX = (
    "[This content was generated with AI assistance and should be "
    "independently verified against primary sources.]"
)
```

**Key decisions:**
- Mandatory disclosures are a *registry*, not scattered across the codebase. One place to look, one place to update.
- AI disclosure is a function, not a convention you remember. Call `require_ai_disclosure()` on any human-facing output.
- The disclosure prefix is a constant that can be overridden in config for different contexts (e.g., shorter version for UI badges vs. full text for documents).

### 3.4 `conventions/identifiers.py` — Universal Identifiers

Every entity in the system gets a universal identifier that remains stable across re-extraction, re-ingestion, and cross-source linking.

```python
import uuid
from enum import StrEnum


class EntityType(StrEnum):
    """All entity types in the system. Used as ID prefixes for human readability."""
    CITY = "city"
    OFFICIAL = "official"
    MEETING = "meeting"
    AGENDA_ITEM = "agenda_item"
    VOTE = "vote"
    MOTION = "motion"
    SPEAKER = "speaker"
    DOCUMENT = "doc"
    DONOR = "donor"
    CONTRIBUTION = "contribution"
    BOARD = "board"           # Boards and commissions
    APPOINTMENT = "appointment"


def generate_id(entity_type: EntityType) -> str:
    """
    Generate a new universal identifier.
    
    Format: {entity_type}_{uuid4_short}
    Example: "official_a1b2c3d4", "meeting_e5f6g7h8"
    
    The prefix makes IDs human-scannable in logs and database queries.
    The UUID portion ensures uniqueness without coordination.
    """


def generate_deterministic_id(entity_type: EntityType, *natural_keys: str) -> str:
    """
    Generate a deterministic ID from natural keys.
    Same inputs always produce the same ID.
    
    Use for entities that might be re-ingested from the same source:
    - A meeting on a specific date: generate_deterministic_id("meeting", "0660620", "2024-01-16")
    - A vote on a specific motion: generate_deterministic_id("vote", meeting_id, motion_number)
    
    This enables idempotent ingestion — re-running extraction on the same
    meeting doesn't create duplicate records.
    
    Format: {entity_type}_{uuid5_from_keys}
    """


def validate_id(entity_id: str) -> tuple[EntityType, str]:
    """
    Validate and parse an entity ID.
    
    Returns:
        Tuple of (EntityType, uuid_portion)
    
    Raises:
        InvalidEntityIDError: If format is wrong or entity type is unknown
    """
```

**Key decisions:**
- Prefixed IDs. `official_a1b2c3d4` is infinitely more debuggable than a raw UUID when you're scanning logs or query results.
- Deterministic IDs for idempotent ingestion. Re-extracting the same meeting produces the same IDs, so upserts work naturally.
- Entity types are an enum, not magic strings. Adding a new entity type means adding it to `EntityType`, which makes it visible and searchable.

### 3.5 `models/base.py` — Base Model

Every data model in the system inherits from this. It enforces FIPS and provides common fields.

```python
from dataclasses import dataclass, field
from datetime import datetime
from civic_sdk.conventions.fips import FIPSMixin
from civic_sdk.conventions.identifiers import generate_id, EntityType


@dataclass
class BaseModel(FIPSMixin):
    """
    Base for all civic data models.
    
    Enforces:
    - city_fips is present and valid (via FIPSMixin)
    - entity_id is present (auto-generated if not provided)
    - created_at and updated_at timestamps
    - source_url for provenance tracking
    """
    entity_id: str = ""           # Set by subclass or auto-generated
    city_fips: str = ""           # REQUIRED — validated by FIPSMixin
    source_url: str = ""          # Where did this data come from?
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Validate all conventions on creation."""
        if not self.city_fips:
            raise MissingFIPSError(
                f"Cannot create {self.__class__.__name__} without city_fips. "
                f"Richmond CA = '0660620'. This is not optional."
            )
        self.city_fips = validate_fips(self.city_fips)
        # entity_id generation delegated to subclasses that know their EntityType
```

**Key decisions:**
- `__post_init__` validation means you literally cannot instantiate a model without valid FIPS. The error message tells you what to do — this is developer experience.
- `source_url` on every record. Every fact in the system is traceable back to where it was found. This is essential for the "sunlight" mission and for debugging extraction errors.
- Timestamps are automatic but overridable (for backfilling historical data).

### 3.6 `db/document_lake.py` — Document Lake Operations

The document lake stores raw documents exactly as received. This is the "re-extractable" layer — when prompts improve, we re-run extraction on the same raw documents.

```python
@require_fips
@require_tier
def store_document(
    content: str | bytes,
    city_fips: str,
    source_tier: SourceTier,
    source_url: str,
    content_type: str,          # "text/html", "application/pdf", "text/plain", etc.
    metadata: dict | None = None,
    document_id: str | None = None,  # If None, auto-generated (deterministic from source_url)
) -> str:
    """
    Store a raw document in the document lake.
    
    The document is stored as-is with JSONB metadata. Nothing is extracted
    or transformed at this stage — that's Layer 2's job.
    
    Returns:
        document_id (str): The universal identifier for this document.
    
    Behavior:
        - If document_id already exists, updates content and metadata (idempotent).
        - Automatically attaches disclosure_note for known Tier 3 sources.
        - Logs the storage event for instrumentation.
    """


@require_fips
def get_document(document_id: str, city_fips: str) -> dict:
    """
    Retrieve a raw document by ID.
    
    Note: city_fips is required even though document_id is globally unique.
    This enforces the habit and enables future table partitioning by city.
    """


@require_fips
def list_documents(
    city_fips: str,
    source_tier: SourceTier | None = None,
    content_type: str | None = None,
    since: datetime | None = None,
) -> list[dict]:
    """List documents with optional filtering. Always scoped to a city."""
```

**Key decisions:**
- The decorators (`@require_fips`, `@require_tier`) do the enforcement. The function body just does the work. Separation of concerns.
- `city_fips` is required on reads too, even though `document_id` is unique. This is deliberate — it enforces the habit and enables partition-by-city if the database grows.
- Idempotent storage by default. Re-ingesting the same URL updates the record instead of duplicating it.

### 3.7 `exceptions.py` — Exception Hierarchy

```python
class CivicSDKError(Exception):
    """Base exception for all SDK errors."""

# Convention violations
class ConventionViolationError(CivicSDKError):
    """Base for convention enforcement failures."""

class MissingFIPSError(ConventionViolationError):
    """Record attempted without city_fips."""

class InvalidFIPSError(ConventionViolationError):
    """FIPS code failed format validation."""

class MissingTierError(ConventionViolationError):
    """Document ingestion attempted without source_tier."""

class InvalidTierError(ConventionViolationError):
    """Source tier is not a valid SourceTier value."""

class MissingTierMetadataError(ConventionViolationError):
    """Required metadata for source tier is missing (e.g., Tier 3 without disclosure)."""

class MissingDisclosureError(ConventionViolationError):
    """Known Tier 3 source ingested without mandatory disclosure."""

# Entity errors
class InvalidEntityIDError(CivicSDKError):
    """Entity ID failed format validation."""

# Database errors  
class DatabaseError(CivicSDKError):
    """Base for database operation failures."""
```

**Key decisions:**
- All exceptions inherit from `CivicSDKError`, so callers can catch everything with one type if needed.
- `ConventionViolationError` is a distinct category. This matters for instrumentation — we want to track how often conventions catch mistakes separately from general errors.
- Error messages are helpful, not cryptic. They tell you what went wrong AND what to do about it.

### 3.8 `logging.py` — Structured Logging

```python
import logging
import json
from datetime import datetime


def get_logger(name: str) -> logging.Logger:
    """
    Get a structured logger for a civic_sdk module.
    
    All log entries include:
    - timestamp
    - module name
    - event_type (one of: convention_enforced, convention_violated,
      document_stored, entity_resolved, query_executed)
    - city_fips (when available)
    
    Convention enforcement events are always logged at INFO level
    so we can measure how often the guardrails activate.
    """


def log_convention_enforced(
    logger: logging.Logger,
    convention: str,       # "fips_validated", "tier_required", "disclosure_attached"
    details: dict,
) -> None:
    """Log a successful convention enforcement."""


def log_convention_violated(
    logger: logging.Logger,
    convention: str,
    details: dict,
) -> None:
    """
    Log a convention violation BEFORE raising the exception.
    This ensures violations are tracked even if the caller catches the exception.
    """
```

**Key decisions:**
- Structured logging (JSON) from the start. When this scales, you need machine-parseable logs.
- Convention enforcement is *always* logged, both successes and violations. "Instrumentation before optimization" — we need to know how often the guardrails fire before we decide whether to tune them.

### 3.9 `config.py` — SDK Configuration

```python
from dataclasses import dataclass


@dataclass
class CivicSDKConfig:
    """
    SDK configuration. Can be loaded from environment variables,
    a config file, or passed directly.
    
    Note: This config is for single-city operation. Multi-city
    configuration management is a Layer 4 concern.
    """
    # Database
    database_url: str = ""
    
    # Default city (convenience for single-city deployments)
    default_city_fips: str = ""       # e.g., "0660620" for Richmond CA
    default_city_name: str = ""       # e.g., "Richmond, California"
    
    # AI disclosure
    ai_disclosure_prefix: str = (
        "[This content was generated with AI assistance and should be "
        "independently verified against primary sources.]"
    )
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"          # "json" or "text"
    
    # Convention enforcement
    strict_mode: bool = True          # If False, log violations instead of raising
                                      # (useful for migration/testing, NOT for production)


def load_config(
    config_path: str | None = None,
    env_prefix: str = "CIVIC_SDK_",
) -> CivicSDKConfig:
    """
    Load configuration from file and/or environment variables.
    Environment variables override file values.
    
    Env var mapping:
        CIVIC_SDK_DATABASE_URL -> database_url
        CIVIC_SDK_DEFAULT_CITY_FIPS -> default_city_fips
        etc.
    """
```

**Key decisions:**
- `default_city_fips` is a convenience, not a bypass. Functions still require FIPS explicitly — this just lets the application layer set it once.
- `strict_mode` exists for migration periods. When onboarding existing data that might not meet all conventions yet, you can log violations instead of crashing. But it defaults to `True` and should stay there in production.
- Environment variable prefix (`CIVIC_SDK_`) keeps config namespace clean.

---

## 4. Cross-Cutting Concerns

### 4.1 Open-Source Boundary

The following MUST NOT appear anywhere in Layers 1-3:
- References to specific proprietary features (multi-city dashboard, subscription management)
- Assumptions about how many cities are configured
- City discovery or auto-onboarding logic
- Any code that only makes sense with 2+ cities

The following SHOULD be in Layers 1-3:
- Single-city operation that works out of the box
- Extension points (base classes, registries, hooks) that Layers 4-5 can plug into
- Documentation that explains how to use the SDK for one city

### 4.2 Testing Strategy

Every convention enforcement module must have tests for:
1. **Happy path:** Valid data passes through
2. **Violation detection:** Invalid data raises the correct exception
3. **Edge cases:** Zero-padding, unusual but valid formats, Unicode in metadata
4. **Instrumentation:** Convention enforcement events are logged

Test file structure mirrors source:
```
tests/
├── conventions/
│   ├── test_fips.py
│   ├── test_tiers.py
│   ├── test_disclosure.py
│   └── test_identifiers.py
├── db/
│   └── test_document_lake.py
├── models/
│   └── test_base.py
└── conftest.py              # Shared fixtures (test DB, sample FIPS codes, etc.)
```

### 4.3 Dependencies

Layer 1 should have minimal dependencies:
- **Python 3.11+** (for StrEnum, modern type hints)
- **psycopg2 or asyncpg** (PostgreSQL)
- **pydantic** (optional — evaluate whether dataclasses are sufficient or if pydantic's validation is worth the dependency)
- No LLM dependencies. No web framework dependencies. No Playwright. Those are Layer 2+.

### 4.4 Future Layer Attachment Points

Layer 1 must provide clean hooks for:

| Future Layer | Attachment Point in Layer 1 |
|---|---|
| **Layer 2: Sources** | `db/document_lake.py` provides storage; `conventions/tiers.py` provides tier validation; `models/` provides base classes for source-specific models |
| **Layer 2: Extraction** | `db/document_lake.py` provides raw content retrieval; `db/structured_core.py` provides storage for extracted data |
| **Layer 3: Entity Resolution** | `conventions/identifiers.py` provides ID generation; `models/official.py` provides the canonical entity model; logging provides match-confidence tracking |
| **Layer 4: Multi-City** | `config.py` provides single-city config that can be composed; `conventions/fips.py` validates any city's FIPS; all DB operations accept city_fips as parameter |
| **Layer 5: Spec Language** | All Layer 1 functions have clean, well-documented APIs that can be referenced by name in specs |

---

## 5. Implementation Sequence

Recommended order for Claude Code to build this:

1. **`exceptions.py`** — Zero dependencies, everything else needs it
2. **`logging.py`** — Nearly zero dependencies, everything else uses it
3. **`config.py`** — Loads configuration that other modules read
4. **`conventions/fips.py`** — Core convention, most other modules depend on it
5. **`conventions/tiers.py`** — Second core convention
6. **`conventions/disclosure.py`** — Depends on tiers
7. **`conventions/identifiers.py`** — Independent of other conventions
8. **`models/base.py`** — Depends on conventions
9. **`models/` (remaining)** — Depend on base
10. **`db/connection.py`** — Depends on config
11. **`db/document_lake.py`** — Depends on conventions, models, connection
12. **`db/schema.py`** — Depends on models
13. **Tests for each module** — Written alongside or immediately after each module

---

## 6. Usage Examples

These examples show what it looks like to USE the SDK once built. They help Claude Code understand the developer experience we're targeting.

### Storing a council meeting document
```python
from civic_sdk.db.document_lake import store_document
from civic_sdk.conventions.tiers import SourceTier

doc_id = store_document(
    content=raw_html,
    city_fips="0660620",
    source_tier=SourceTier.OFFICIAL,
    source_url="https://richmond.legistar.com/meetings/2024-01-16",
    content_type="text/html",
    metadata={"meeting_date": "2024-01-16", "body": "City Council"},
)
```

### Attempting to skip FIPS (this should FAIL)
```python
# This raises MissingFIPSError — you cannot skip FIPS, ever
doc_id = store_document(
    content=raw_html,
    source_tier=SourceTier.OFFICIAL,
    source_url="https://richmond.legistar.com/meetings/2024-01-16",
    content_type="text/html",
)
# MissingFIPSError: Cannot store document without city_fips.
# Richmond CA = '0660620'. This is not optional.
```

### Ingesting a Tier 3 source without disclosure (this should FAIL)
```python
# This raises MissingTierMetadataError — Tier 3 requires disclosure
doc_id = store_document(
    content=article_html,
    city_fips="0660620",
    source_tier=SourceTier.STAKEHOLDER,
    source_url="https://richmondstandard.com/some-article",
    content_type="text/html",
    # Missing metadata={"disclosure_note": "Funded by Chevron Richmond"}
)
# MissingTierMetadataError: STAKEHOLDER tier requires: disclosure_note
```

### Creating an official record
```python
from civic_sdk.models.official import Official

official = Official(
    city_fips="0660620",
    name="Eduardo Martinez",
    title="Mayor",
    body="City Council",
    source_url="https://www.ci.richmond.ca.us/1382/City-Council",
)
# official.entity_id is auto-generated: "official_a1b2c3d4"
```

---

## 7. Open Questions for Review

Before Claude Code starts building, the operator should weigh in on:

1. **Pydantic vs. dataclasses?** Pydantic gives us richer validation out of the box but adds a dependency. Dataclasses keep things lighter but mean we write more validation code ourselves. Recommendation: Start with pydantic — the validation is exactly what Layer 1 is about, and it's a well-known library that makes the SDK feel professional for open-source consumers.

2. **Package name:** `civic_sdk` vs. `civic_transparency_sdk` vs. `civicsdk` vs. something else? This matters for the eventual PyPI package name. Shorter is generally better.

3. **License for open-source layers:** MIT (maximum adoption) vs. Apache 2.0 (patent protection) vs. AGPL (forces contributions back). Recommendation: Apache 2.0 — good balance of openness and protection.

4. **Python version floor:** 3.11+ (for StrEnum, modern features) vs. 3.10 (wider compatibility)? Recommendation: 3.11+ unless there's a reason to support older versions.

5. **Async from the start?** Should DB operations be async (asyncpg) or sync (psycopg2)? Async is better for pipeline performance but adds complexity. Recommendation: Async, since the pipeline will be doing a lot of concurrent I/O (fetching multiple sources, storing multiple documents).

---

## 8. Relationship to Existing Codebase

This SDK should be built as a new Python package within the existing `richmond-common` repo, probably at `packages/civic_sdk/` or `libs/civic_sdk/`. It does NOT replace existing pipeline code immediately — instead, existing code is gradually refactored to use the SDK's conventions and models.

Migration path:
1. Build the SDK alongside existing code
2. New pipeline features use the SDK from day one
3. Existing code is refactored module by module to use SDK functions
4. Once migration is complete, the SDK can be extracted to its own repo for open-sourcing

---

*This spec is a living document. Update it as implementation reveals better approaches.*
