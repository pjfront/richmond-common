"""Source-backed regression for contribution direction and filing identity.

The real committee example is from Richmond, California NetFile filing
216841017, fetched September 6, 2026. Its PDF labels Part 2 as contributions
made by RPOA PAC to Safe Richmond Neighborhoods, with amendment unchecked:
https://netfile.com/Connect2/api/public/image/216841017
"""
import pytest

from netfile_client import extract_filers, normalize_transaction


RPOA = "Richmond Police Officers Association PAC, Sponsored by Richmond Police Officers Association"
SAFE_RICHMOND = (
    "Safe Richmond Neighborhoods supporting Ahmad Anderson for Mayor 2026 "
    "sponsored by the Richmond Police Officers Association"
)


def test_part2_preserves_real_donor_to_recipient_direction():
    raw = {
        "id": "fa1ba819-249c-40e5-9a57-b45a01461217",
        "filingId": "216841017",
        "filerFppcId": "951606",
        "filerLocalId": "RICH-112789",
        "filerName": RPOA,
        "date": "2026-05-29T00:00:00-07:00",
        "amount": 30000.0,
        "transactionType": 21,
        "name": SAFE_RICHMOND,
        "transactionFppcId": "1490887",
        "city": "Oakland",
        "state": "CA",
        "zip": "94607",
    }
    row = normalize_transaction(raw)

    assert row["contributor_name"] == RPOA
    assert row["contributor_fppc_id"] == "951606"
    assert row["committee"] == SAFE_RICHMOND
    assert row["filer_fppc_id"] == "1490887"
    assert row["filer_local_id"] == ""
    assert row["amount"] == 30000
    assert row["date"] == "2026-05-29"
    assert row["filing_id"] == "216841017"
    assert row["transaction_id"] == raw["id"]
    assert row["transaction_type"] == "F497P2"
    # An outgoing report is evidence of RPOA's e-filing, not evidence
    # that the recipient files electronically. Preserve paper discovery.
    assert extract_filers([row]) == [{
        "fppc_id": "951606",
        "local_id": "RICH-112789",
        "name": RPOA,
        "source": "netfile",
        "city_fips": "0660620",
    }]
    assert (row["city"], row["state"], row["zip"]) == ("", "", "")


@pytest.mark.parametrize("transaction_type, form", [(0, "F460A"), (1, "F460C"), (20, "F497P1")])
def test_received_reports_keep_contributor_details_and_recipient_identity(transaction_type, form):
    row = normalize_transaction({
        "transactionType": transaction_type,
        "filerName": "Candidate committee",
        "filerFppcId": "recipient-id",
        "filerLocalId": "recipient-local",
        "name": "Contributing committee",
        "transactionFppcId": "donor-id",
        "amount": 1000,
        "date": "2026-08-20T00:00:00-07:00",
        "employer": "Donor employer",
        "occupation": "Donor occupation",
        "city": "Richmond",
        "state": "CA",
        "zip": "94804",
        "code": "COM",
    })
    assert row["contributor_name"] == "Contributing committee"
    assert row["contributor_fppc_id"] == "donor-id"
    assert row["committee"] == "Candidate committee"
    assert row["filer_fppc_id"] == "recipient-id"
    assert row["filer_local_id"] == "recipient-local"
    assert row["transaction_type"] == form
    assert row["entity_code"] == "COM"
    assert row["contributor_employer"] == "Donor employer"
    assert row["occupation"] == "Donor occupation"
    assert (row["city"], row["state"], row["zip"]) == ("Richmond", "CA", "94804")


def test_part2_does_not_assign_recipient_attributes_or_fallback_id_to_donor():
    row = normalize_transaction({
        "transactionType": 21,
        "filerName": "Donating committee",
        "filerFppcId": "donor-id",
        "filerLocalId": "donor-local",
        "name": "Recipient with no assigned FPPC ID",
        "transactionFppcId": None,
        "employer": "Recipient employer",
        "occupation": "Recipient occupation",
        "city": "Recipient city",
        "state": "CA",
        "zip": "00000",
        "code": "IND",
    })
    assert row["filer_fppc_id"] == ""
    assert row["filer_local_id"] == ""
    assert row["entity_code"] is None
    assert row["contributor_employer"] == ""
    assert row["occupation"] == ""
    assert row["reporting_filer_fppc_id"] == "donor-id"
    assert (row["city"], row["state"], row["zip"]) == ("", "", "")
