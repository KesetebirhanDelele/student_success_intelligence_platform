from __future__ import annotations

TRANSITIONS: dict[str, set[str]] = {
    "ELIGIBLE":               {"QUEUED", "CLOSED"},
    "QUEUED":                 {"CONTACTED", "CLOSED"},
    "CONTACTED":              {"NO_RESPONSE", "RESPONDED", "CLOSED", "INTERVENTION_REQUIRED"},
    "NO_RESPONSE":            {"RETRY", "CLOSED", "INTERVENTION_REQUIRED"},
    "RETRY":                  {"CONTACTED", "CLOSED", "INTERVENTION_REQUIRED"},
    "RESPONDED":              {"ANALYZED", "RESOLVED", "CLOSED", "INTERVENTION_REQUIRED"},
    "ANALYZED":               {"INTERVENTION_REQUIRED", "RESOLVED", "CLOSED"},
    "INTERVENTION_REQUIRED":  {"RESOLVED", "CLOSED"},
    "RESOLVED":               {"CLOSED"},
    "CLOSED":                 set(),
}

TERMINAL: set[str] = {"CLOSED"}


class StateViolationError(Exception):
    pass


def validate_transition(from_state: str, to_state: str, trigger: str = "") -> None:
    allowed = TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise StateViolationError(
            f"Invalid transition {from_state} → {to_state} (trigger={trigger!r}). "
            f"Allowed: {allowed or 'none — terminal state'}"
        )


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in TRANSITIONS.get(from_state, set())


def is_terminal(state: str) -> bool:
    return state in TERMINAL
