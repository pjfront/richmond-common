# tests/test_form700_netfile_api.py
"""Unit tests for the NetFile SEI JSON API client (src/form700_netfile_api.py).

Covers the pure mapping/joining logic against fixtures shaped exactly like
real API responses captured 2026-07-05 (S28.1). No network calls.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from form700_netfile_api import (  # noqa: E402
    build_filing_records,
    transaction_to_interests,
    _filing_year,
    _statement_type_from_cover,
)


def _txn(template, content, filer="Bana, Soheila", start="2025-01-01T08:00:00Z",
         superseded=False):
    """Transaction item shaped like api/searchtransactions output."""
    return {
        "templateName": template,
        "filerName": filer,
        "periodStart": start,
        "periodEnd": "2026-01-01T07:59:58Z",
        "isSuperceded": superseded,
        "isArchived": False,
        "filingId": 216508680,
        "content": json.dumps(content),
    }


def _filing(filer="Bana, Soheila", form="fppc700_2026", start="2025-01-01T00:00:00",
            superseded=False, position="City Council Member"):
    """Filing header shaped like api/searchfilings output."""
    return {
        "filerName": filer,
        "formName": form,
        "filingDate": "2026-04-01T12:00:00",
        "periodStart": start,
        "periodEnd": "2025-12-31T00:00:00",
        "isSuperceded": superseded,
        "isPubliclyVisible": False,  # False on every real filing — must not filter
        "positionName": position,
        "filingId": "4612f924-de26-408f-8828-ee1cd93a8fdf",
    }


class TestTransactionMapping:
    def test_schedule_b_real_property(self):
        interests = transaction_to_interests(_txn("ScheduleB", {
            "City": "Richmond",
            "FairMarketValueAsString": "$100,001 - $1,000,000",
            "NatureOfInterestAsString": "Ownership/Deed of Trust",
            "ParcelOrAddress": "727 Devils Drop Court",
        }))
        assert len(interests) == 1
        i = interests[0]
        assert i["schedule"] == "B"
        assert i["interest_type"] == "real_property"
        assert "727 Devils Drop Court" in i["description"]
        assert i["value_range"] == "$100,001 - $1,000,000"
        assert i["location"] == "Richmond"

    def test_schedule_a1_investment_fmv_enum(self):
        interests = transaction_to_interests(_txn("ScheduleA1", {
            "NameOfBusinessEntity": "Deutsche Bank",
            "DescriptionAsString": "Investment bank",
            "NatureOfInvestmentAsString": "Other Trust",
            "FairMarketValue": 2,
        }))
        assert interests[0]["interest_type"] == "investment"
        assert "Deutsche Bank" in interests[0]["description"]
        assert interests[0]["value_range"] == "$10,001 - $100,000"

    def test_schedule_c_income_no_value_guessing(self):
        """C income enum tiers aren't portal-rendered — value_range stays None."""
        interests = transaction_to_interests(_txn("ScheduleC", {
            "NameOfIncomeSource": "Jafran, Inc.",
            "BusinessActivity": "Real Estate",
            "BusinessPosition": "Realtor",
            "ReasonForIncomeAsString": "Commission",
            "GrossIncomeReceivedScheduleC1": 5,
            "Address": {"City": "San Ramon"},
        }))
        i = interests[0]
        assert i["interest_type"] == "income"
        assert "Jafran, Inc." in i["description"]
        assert i["value_range"] is None
        assert i["location"] == "San Ramon"

    def test_schedule_d_splits_gifts(self):
        interests = transaction_to_interests(_txn("ScheduleD", {
            "NameOfSource": "Noracal Carpenters Union",
            "Address": {"City": "Oakland"},
            "Gifts": [
                {"Amount": 100.0, "Description": "Dinner", "GiftDate": "2023-12-15T00:00:00"},
                {"Amount": 75.5, "Description": "Tickets", "GiftDate": "2023-10-01T00:00:00"},
            ],
        }))
        assert len(interests) == 2
        assert all(i["interest_type"] == "gift" for i in interests)
        assert interests[0]["value_range"] == "$100.00"
        assert "Dinner" in interests[0]["description"]

    def test_schedule_e_travel(self):
        interests = transaction_to_interests(_txn("ScheduleE", {
            "NameOfSource": "Water Education for Latino Leaders",
            "TravelDescription": "Sacramento",
            "TypeOfPaymentAsString": "Gift estimated cost of hotel accomodations",
            "Amount": 120.0,
            "StartDate": "2018-03-23T00:00:00",
            "Address": {"City": "Los Angeles"},
        }))
        i = interests[0]
        assert i["interest_type"] == "travel"
        assert i["schedule"] == "E"
        assert i["value_range"] == "$120.00"

    def test_unknown_template_returns_empty(self):
        assert transaction_to_interests(_txn("Comment", {})) == []


class TestFilingYearAndStatementType:
    def test_filing_year_from_form_name(self):
        assert _filing_year({"formName": "fppc700_2026", "filingDate": "2026-04-01"}) == 2026

    def test_filing_year_falls_back_to_filing_date(self):
        assert _filing_year({"formName": "Unknown", "filingDate": "2024-02-26T10:00:00"}) == 2024

    def test_statement_type_flags(self):
        assert _statement_type_from_cover({"StatementType": {"IsAnnual": True}}) == "annual"
        assert _statement_type_from_cover({"StatementType": {"IsAssuming": True}}) == "assuming_office"
        assert _statement_type_from_cover({"StatementType": {"IsLeaving": True}}) == "leaving_office"
        assert _statement_type_from_cover({"StatementType": {"IsCandidate": True}}) == "candidate"
        assert _statement_type_from_cover({}) is None


class TestBuildFilingRecords:
    def test_nearest_start_join_tolerates_day_offsets(self):
        """Filing header says Jan 1; line items carry the assumption date
        days later (real case: Bana 2023-01-01 vs 2023-01-11)."""
        filings = [_filing(start="2023-01-01T00:00:00", form="fppc700_2024")]
        txns = [_txn("ScheduleB", {"City": "Richmond", "ParcelOrAddress": "1 Elm St",
                                   "NatureOfInterestAsString": "Ownership"},
                     start="2023-01-11T08:00:00Z")]
        records = build_filing_records(filings, txns)
        assert len(records) == 1
        assert len(records[0]["extraction"]["interests"]) == 1
        assert records[0]["extraction"]["no_interests_declared"] is False

    def test_group_beyond_tolerance_is_dropped_not_misattached(self):
        filings = [_filing(start="2023-01-01T00:00:00")]
        txns = [_txn("ScheduleB", {"City": "Richmond", "ParcelOrAddress": "1 Elm St",
                                   "NatureOfInterestAsString": "Ownership"},
                     start="2021-04-07T08:00:00Z")]
        records = build_filing_records(filings, txns)
        assert records[0]["extraction"]["interests"] == []

    def test_superseded_filings_and_txns_skipped(self):
        filings = [
            _filing(superseded=True),
            _filing(superseded=False),
        ]
        txns = [
            _txn("ScheduleB", {"City": "Richmond", "ParcelOrAddress": "1 Elm St",
                               "NatureOfInterestAsString": "Ownership"}, superseded=True),
        ]
        records = build_filing_records(filings, txns)
        assert len(records) == 1  # superseded filing dropped
        assert records[0]["extraction"]["interests"] == []  # superseded txn dropped

    def test_no_interests_declared_when_no_line_items(self):
        records = build_filing_records([_filing()], [])
        rec = records[0]
        assert rec["extraction"]["no_interests_declared"] is True
        assert rec["extraction"]["extraction_confidence"] == 1.0
        assert rec["filing_metadata"]["filing_year"] == 2026
        assert rec["filing_metadata"]["source"] == "netfile_sei"

    def test_exact_duplicate_interests_collapse(self):
        content = {"City": "Richmond", "ParcelOrAddress": "1 Elm St",
                   "NatureOfInterestAsString": "Ownership"}
        records = build_filing_records(
            [_filing()],
            [_txn("ScheduleB", content), _txn("ScheduleB", content)],
        )
        assert len(records[0]["extraction"]["interests"]) == 1

    def test_cover_sets_statement_type(self):
        records = build_filing_records(
            [_filing()],
            [_txn("Cover", {"StatementType": {"IsAssuming": True}})],
        )
        assert records[0]["filing_metadata"]["statement_type"] == "assuming_office"
