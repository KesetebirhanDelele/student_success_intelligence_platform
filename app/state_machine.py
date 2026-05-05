from typing import Set, Dict

# All valid lifecycle states
VALID_STATES: Set[str] = {
    "ELIGIBLE",
    "QUEUED",
    "CONTACTED",
    "NO_RESPONSE",
    "RESPONDED",
    "ANALYZED",
    "INTERVENTION_REQUIRED",
    "MEETING_SCHEDULED",
    "RESOLVED",
    "CLOSED",
}

# Terminal state — no further transitions allowed
TERMINAL_STATE = "CLOSED"

# Allowed transitions: from_state → set of valid to_states
TRANSITIONS: Dict[str, Set[str]] = {
    "ELIGIBLE":               {"QUEUED", "CLOSED"},
    "QUEUED":                 {"CONTACTED", "CLOSED"},
    "CONTACTED":              {"NO_RESPONSE", "RESPONDED", "CLOSED"},
    "NO_RESPONSE":            {"QUEUED", "CLOSED"},         # QUEUED = retry cycle
    "RESPONDED":              {"ANALYZED", "RESOLVED", "CLOSED"},
    "ANALYZED":               {"INTERVENTION_REQUIRED", "RESOLVED", "CLOSED"},
    "INTERVENTION_REQUIRED":  {"MEETING_SCHEDULED", "CLOSED"},
    "MEETING_SCHEDULED":      {"RESOLVED", "CLOSED"},
    "RESOLVED":               {"CLOSED"},
    "CLOSED":                 set(),                         # terminal
}


class StateViolationError(Exception):
    pass


def validate_transition(current: str, target: str) -> None:
    """Raise StateViolationError if the transition is not permitted."""
    if current not in VALID_STATES:
        raise StateViolationError(f"Unknown current state: {current}")
    if target not in VALID_STATES:
        raise StateViolationError(f"Unknown target state: {target}")
    if target not in TRANSITIONS.get(current, set()):
        raise StateViolationError(
            f"Invalid transition: {current} → {target}"
        )


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def is_terminal(state: str) -> bool:
    return state == TERMINAL_STATE
