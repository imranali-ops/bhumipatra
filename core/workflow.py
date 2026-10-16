"""Mutation (নামজারি) workflow as a small, strictly checked state machine.

    submitted --survey_verify--> survey_verified --approve--> approved
        |  \\--survey_reject--> rejected      \\--reject---> rejected
        \\--cancel (applicant)--> cancelled
"""
from __future__ import annotations

SUBMITTED = "submitted"
SURVEY_VERIFIED = "survey_verified"
APPROVED = "approved"
REJECTED = "rejected"
CANCELLED = "cancelled"

ACTIVE_STATUSES = frozenset({SUBMITTED, SURVEY_VERIFIED})
FINAL_STATUSES = frozenset({APPROVED, REJECTED, CANCELLED})

TRANSITIONS = {
    (SUBMITTED, "survey_verify"): (SURVEY_VERIFIED, frozenset({"surveyor"})),
    (SUBMITTED, "survey_reject"): (REJECTED, frozenset({"surveyor"})),
    (SUBMITTED, "cancel"): (CANCELLED, frozenset({"citizen"})),
    (SURVEY_VERIFIED, "approve"): (APPROVED, frozenset({"ac_land"})),
    (SURVEY_VERIFIED, "reject"): (REJECTED, frozenset({"ac_land"})),
}
ACTIONS = frozenset(action for (_, action) in TRANSITIONS)
NOTE_REQUIRED = frozenset({"survey_verify", "survey_reject", "reject"})


class InvalidTransition(Exception):
    """The action is not possible in the application's current status."""


class RoleNotAllowed(Exception):
    """The action exists but this role may not perform it."""


def next_status(status: str, action: str, role: str) -> str:
    key = (status, action)
    if key not in TRANSITIONS:
        raise InvalidTransition(f"action '{action}' is not possible when status is '{status}'")
    new_status, roles = TRANSITIONS[key]
    if role not in roles:
        raise RoleNotAllowed(f"role '{role}' may not perform '{action}'")
    return new_status
