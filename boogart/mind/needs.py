from __future__ import annotations

from datetime import datetime

from boogart.core.growth import parse_timestamp
from boogart.core.state import BoogartState
from boogart.mind.appraisal import AppraisalResult


def apply_need_drift(state: BoogartState, appraisal: AppraisalResult, now: datetime) -> None:
    elapsed_minutes = max(0, int((now - parse_timestamp(state.updated_at)).total_seconds() // 60))
    hunger_delta = elapsed_minutes // 30
    loneliness_delta = elapsed_minutes // 120

    state.hunger = clamp(state.hunger + hunger_delta + appraisal.pressure.get("hunger", 0) // 10)
    state.corruption = clamp(state.corruption + appraisal.pressure.get("corruption", 0) // 4)

    needs = ensure_need_memory(state)
    needs["fear"] = clamp(needs.get("fear", 0) + appraisal.pressure.get("fear", 0))
    needs["curiosity"] = clamp(needs.get("curiosity", 0) + appraisal.pressure.get("curiosity", 0))
    needs["loneliness"] = clamp(needs.get("loneliness", 0) + loneliness_delta + appraisal.pressure.get("loneliness", 0))
    needs["trust"] = clamp(needs.get("trust", 0) + appraisal.pressure.get("affection", 0))


def ensure_need_memory(state: BoogartState) -> dict[str, int]:
    raw = state.memory.setdefault("needs", {})
    if not isinstance(raw, dict):
        raw = {}
        state.memory["needs"] = raw

    needs: dict[str, int] = {}
    for key in ("fear", "curiosity", "loneliness", "trust"):
        needs[key] = int(raw.get(key, 0) or 0)
    state.memory["needs"] = needs
    return needs


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, value))
