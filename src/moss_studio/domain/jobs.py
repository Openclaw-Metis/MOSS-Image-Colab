"""Job transitions; interrupted jobs never become successful without history reconciliation."""

from moss_studio.domain.contracts import ValidationError

TERMINAL = frozenset({"succeeded", "failed", "cancelled", "interrupted"})
PIPELINE = ("created", "validating", "queued", "encoding", "sampling", "decoding", "saving")
TRANSITIONS = {
    state: {
        PIPELINE[i + 1] if i + 1 < len(PIPELINE) else "succeeded",
        "failed",
        "cancelling",
        "interrupted",
    }
    for i, state in enumerate(PIPELINE)
}
TRANSITIONS["cancelling"] = {"cancelled", "failed", "interrupted"}
TRANSITIONS.update({state: set() for state in TERMINAL})


def validate_transition(previous: str, target: str) -> None:
    if target not in TRANSITIONS.get(previous, set()):
        raise ValidationError(f"不允許工作狀態 {previous} → {target}")
