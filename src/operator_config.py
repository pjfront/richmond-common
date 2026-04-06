"""Operator-configurable scan parameters.

Reads per-city configuration from the operator_config table (migration 074).
Uses contextvars so config is set once at the pipeline entry point and
accessible anywhere in the call chain without signature changes.

DEFAULT_CONFIG mirrors all hardcoded constants from conflict_scanner.py and
completeness_monitor.py — zero behavioral change when no DB row exists.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanConfig:
    """Five JSONB column groups from operator_config table."""
    publication: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    temporal: dict[str, Any] = field(default_factory=dict)
    financial: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)


# Defaults exactly mirror current hardcoded constants.
DEFAULT_CONFIG = ScanConfig(
    publication={
        "tier_high": 0.85,
        "tier_medium": 0.70,
        "tier_low": 0.50,
        "hedge_enabled": True,
        "hedge_text": "Other explanations may exist.",
        "blocklist": [
            "corruption", "corrupt",
            "illegal", "illegally",
            "bribery", "bribe", "kickback",
            "scandal", "scandalous",
            "suspicious", "suspiciously",
        ],
    },
    evidence={
        "match_strength": 0.35,
        "temporal_factor": 0.25,
        "financial_factor": 0.20,
        "anomaly_factor": 0.20,
        "sitting_mult": 1.0,
        "non_sitting_mult": 0.6,
        "corroboration_2": 1.15,
        "corroboration_3plus": 1.30,
    },
    temporal={
        "bands": [
            {"days": 90, "factor": 1.0},
            {"days": 180, "factor": 0.8},
            {"days": 365, "factor": 0.6},
            {"days": 730, "factor": 0.4},
        ],
        "beyond_factor": 0.2,
        "post_vote_penalty": 0.70,
        "anomaly_boost_days": 30,
        "anomaly_boost_amount": 0.10,
    },
    financial=[
        {"min": 5000, "factor": 1.0},
        {"min": 1000, "factor": 0.7},
        {"min": 500, "factor": 0.5},
        {"min": 100, "factor": 0.3},
        {"min": 0, "factor": 0.1},
    ],
    quality={
        "weight_items": 30,
        "weight_votes": 30,
        "weight_attendance": 20,
        "weight_urls": 20,
        "anomaly_stddev": 2.0,
        "min_baselines": 50,
        "default_anomaly": 0.5,
    },
)


_config: ContextVar[ScanConfig | None] = ContextVar("scan_config", default=None)


def set_scan_config(config: ScanConfig) -> Token:
    """Set scan config for the current context. Returns a reset token."""
    return _config.set(config)


def get_scan_config() -> ScanConfig:
    """Read current scan config, falling back to DEFAULT_CONFIG."""
    v = _config.get()
    return v if v is not None else DEFAULT_CONFIG


def load_from_db(conn: Any, city_fips: str) -> ScanConfig:
    """Read operator_config from the database for a city.

    Returns DEFAULT_CONFIG if no row exists or the table is missing.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT publication, evidence, temporal, financial, quality
                FROM operator_config
                WHERE city_fips = %s
                """,
                (city_fips,),
            )
            row = cur.fetchone()

        if not row:
            return DEFAULT_CONFIG

        publication, evidence, temporal, financial, quality = row

        return ScanConfig(
            publication=publication if isinstance(publication, dict) else DEFAULT_CONFIG.publication,
            evidence=evidence if isinstance(evidence, dict) else DEFAULT_CONFIG.evidence,
            temporal=temporal if isinstance(temporal, dict) else DEFAULT_CONFIG.temporal,
            financial=financial if isinstance(financial, list) else DEFAULT_CONFIG.financial,
            quality=quality if isinstance(quality, dict) else DEFAULT_CONFIG.quality,
        )
    except Exception:
        # Table may not exist yet — graceful fallback
        return DEFAULT_CONFIG
