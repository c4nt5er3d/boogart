from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boogart.core.filesystem import FileSystemAdapter
from boogart.core.growth import stage_for_created_at
from boogart.core.lifecycle import apply_death_rule_updates, evaluate_death_rules
from boogart.core.state import BoogartState
from boogart.mind.appraisal import AppraisalResult, appraise
from boogart.mind.actions import DEFAULT_ACTIONS, BrainAction
from boogart.mind.context import BrainContext, BrainResult
from boogart.mind.needs import ensure_need_memory
from boogart.mind.score import ActionScore
from boogart.world.observations import FileObservation, PlaceProfile
from boogart.world.scanner import scan_folder


class UtilityBrain:
    def __init__(self, actions: tuple[BrainAction, ...] = DEFAULT_ACTIONS) -> None:
        self.actions = actions

    def tick(self, ctx: BrainContext) -> BrainResult:
        if ctx.state.lifecycle == "alive":
            ctx.state.stage = stage_for_created_at(ctx.state.birth_at, ctx.now).id

        apply_death_rule_updates(ctx.state, evaluate_death_rules(ctx.state, ctx.place, ctx.observations, ctx.now))
        scored = [(action.score(ctx), action) for action in self.actions]
        best_score = ActionScore(0)
        best_action: BrainAction | None = None

        for score, action in scored:
            if score.value > best_score.value:
                best_score = score
                best_action = action

        if not best_action or best_score.value <= 0:
            return BrainResult("idle")
        ctx.state.memory["last_brain_score"] = {
            "action": best_action.id,
            "score": best_score.value,
            "reasons": list(best_score.reasons),
        }
        result = best_action.run(ctx)
        ctx.state.updated_at = ctx.now.isoformat(timespec="seconds")
        return result


def tick_state(
    state: BoogartState,
    folder: Path,
    now: datetime | None = None,
    brain: UtilityBrain | None = None,
    fs: FileSystemAdapter | None = None,
    place: PlaceProfile | None = None,
    observations: list[FileObservation] | None = None,
    appraisal: AppraisalResult | None = None,
    needs: dict[str, int] | None = None,
) -> BrainResult:
    current_time = now or datetime.now(timezone.utc)
    filesystem = fs or FileSystemAdapter((folder,))
    current_place, current_observations = (place, observations) if place is not None and observations is not None else scan_folder(folder, generated_files=state.generated_files)
    current_appraisal = appraisal or appraise(current_place, current_observations)
    current_needs = needs or ensure_need_memory(state)
    ctx = BrainContext(
        state=state,
        folder=folder,
        place=current_place,
        observations=current_observations,
        now=current_time,
        fs=filesystem,
        appraisal=current_appraisal,
        needs=current_needs,
    )
    return (brain or UtilityBrain()).tick(ctx)
