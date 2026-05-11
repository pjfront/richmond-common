"""Signal detectors. One v3 signal per module."""

from .campaign_contribution import signal_campaign_contribution  # noqa: F401
from .form700 import signal_form700_property, signal_form700_income  # noqa: F401
from .temporal_correlation import signal_temporal_correlation  # noqa: F401
from .donor_vendor import signal_donor_vendor_expenditure  # noqa: F401
from .independent_expenditure import signal_independent_expenditure  # noqa: F401
from .permit_donor import signal_permit_donor  # noqa: F401
from .license_donor import signal_license_donor  # noqa: F401
from .llc_ownership import signal_llc_ownership_chain  # noqa: F401
from .behested_payment import signal_behested_payment, signal_behested_payment_loop  # noqa: F401
from .unregistered_lobbyist import signal_unregistered_lobbyist  # noqa: F401

__all__ = [
    'signal_campaign_contribution',
    'signal_form700_property',
    'signal_form700_income',
    'signal_temporal_correlation',
    'signal_donor_vendor_expenditure',
    'signal_independent_expenditure',
    'signal_permit_donor',
    'signal_license_donor',
    'signal_llc_ownership_chain',
    'signal_behested_payment',
    'signal_behested_payment_loop',
    'signal_unregistered_lobbyist',
]
