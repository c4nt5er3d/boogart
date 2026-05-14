from __future__ import annotations

import random
from datetime import timedelta
from pathlib import Path

from boogart.core.lifecycle import (
    DeathCause,
    can_rebirth,
    first_death_cause,
    kill_boogart,
    rebirth,
    refresh_corpse_rot,
    track_generated_file,
)
from boogart.mind.context import BrainContext, BrainResult
from boogart.mind.rooms import choose_room, remember_room_visit
from boogart.mind.score import ActionScore
from boogart.mind import tuning
from boogart.world.hazards import daily_hazard_name
from boogart.world.scope import ROOM_MARKER


class BrainAction:
    id = "action"

    def score(self, ctx: BrainContext) -> ActionScore:
        raise NotImplementedError

    def run(self, ctx: BrainContext) -> BrainResult:
        raise NotImplementedError


class RebirthAction(BrainAction):
    id = "rebirth"

    def score(self, ctx: BrainContext) -> ActionScore:
        if can_rebirth(ctx.state, ctx.now):
            return ActionScore.because(tuning.REBIRTH_SCORE, "rebirth available")
        return ActionScore(0)

    def run(self, ctx: BrainContext) -> BrainResult:
        old_incarnation = ctx.state.incarnation_id
        rebirth(ctx.state, ctx.now)
        return BrainResult(self.id, f"reborn after {old_incarnation}")


class DieAction(BrainAction):
    id = "die"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        cause = first_death_cause(ctx.state, ctx.place, ctx.observations, ctx.now)
        if cause:
            return ActionScore.because(tuning.DEATH_SCORE, f"death cause: {cause.id}")
        return ActionScore(0)

    def run(self, ctx: BrainContext) -> BrainResult:
        cause = first_death_cause(ctx.state, ctx.place, ctx.observations, ctx.now) or DeathCause("unknown", "something ended")
        path = kill_boogart(ctx.state, ctx.folder, cause, ctx.now)
        return BrainResult(self.id, f"death:{cause.id}", path)


class EatCorpseAction(BrainAction):
    id = "eat_corpse"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        if ctx.state.hunger < 95:
            return ActionScore(0)
        if ctx.place.food_count:
            return ActionScore(0)
        if ctx.state.corruption < 40 and ctx.state.stage not in {"changed", "final"}:
            return ActionScore(0)
        corpse = self._available_corpse(ctx)
        if corpse:
            return ActionScore.because(tuning.EAT_CORPSE_SCORE, "corpse available")
        return ActionScore(0)

    def run(self, ctx: BrainContext) -> BrainResult:
        corpse = self._available_corpse(ctx)
        if not corpse:
            return BrainResult(self.id, "no corpse")

        corpse_path = Path(str(corpse["corpse_path"]))
        stain_path = corpse_path.with_name("stain_boogart.png")
        ctx.fs.replace_owned(ctx.state, corpse_path, stain_path)

        corpse["eaten"] = True
        ctx.state.corruption = min(100, ctx.state.corruption + 25)
        ctx.state.memory["ate_dead_boogart"] = True
        ctx.state.global_memory["ate_corpse"] = True
        return BrainResult(self.id, "corpse eaten", stain_path)

    def _available_corpse(self, ctx: BrainContext) -> dict[str, object] | None:
        for corpse in ctx.state.corpse_records:
            if not corpse.get("eaten") and corpse.get("folder_path") == str(ctx.folder):
                return corpse
        return None


class EatFoodAction(BrainAction):
    id = "eat_food"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        foods = [item for item in ctx.observations if item.edible]
        if foods:
            hunger_pressure = ctx.appraisal.pressure.get("hunger", 0)
            return ActionScore.because(
                tuning.EAT_FOOD_BASE_SCORE + ctx.state.hunger + hunger_pressure,
                f"found {len(foods)} foods",
                f"hunger {ctx.state.hunger}",
            )
        return ActionScore(0)

    def run(self, ctx: BrainContext) -> BrainResult:
        foods = sorted((item for item in ctx.observations if item.edible), key=lambda item: food_score(item.name), reverse=True)
        if not foods:
            return BrainResult(self.id, "no food")

        food = foods[0]
        ctx.fs.delete_food(food.path)
        ctx.state.hunger = max(0, ctx.state.hunger - 45)
        ctx.state.affection += 1
        ctx.state.memory["last_food_eaten"] = food.name
        return BrainResult(self.id, f"ate {food.name}", food.path)


class AvoidHazardAction(BrainAction):
    id = "avoid_hazard"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        if ctx.place.hazard_count:
            fear = ctx.needs.get("fear", 0)
            return ActionScore.because(
                tuning.AVOID_HAZARD_BASE_SCORE + ctx.place.hazard_count + fear,
                f"hazards: {ctx.place.hazard_count}",
                f"fear {fear}",
            )
        return ActionScore(0)

    def run(self, ctx: BrainContext) -> BrainResult:
        ctx.state.memory["saw_hazard_at"] = str(ctx.folder)
        ctx.state.neglect += 1
        return BrainResult(self.id, "unsafe here")


class SeedDailyHazardAction(BrainAction):
    id = "seed_daily_hazard"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        today = ctx.now.date().isoformat()
        if ctx.state.memory.get("last_hazard_day") == today:
            return ActionScore(0)
        if ctx.state.stage in {"newborn", "baby_kitten"}:
            return ActionScore(0)
        return ActionScore.because(tuning.SEED_DAILY_HAZARD_SCORE, "hazard daily")

    def run(self, ctx: BrainContext) -> BrainResult:
        path = ctx.folder / daily_hazard_name(ctx.now.date(), ctx.state.run_id)
        if not path.exists():
            ctx.fs.write_owned_text(ctx.state, path, "unsafe for boogart\n")
        else:
            track_generated_file(ctx.state, path)
        ctx.state.memory["last_hazard_day"] = ctx.now.date().isoformat()
        return BrainResult(self.id, f"hazard:{path.name}", path)


class ReactToCorpseAction(BrainAction):
    id = "react_to_corpse"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        if ctx.place.corpse_count:
            fear = ctx.needs.get("fear", 0)
            return ActionScore.because(tuning.REACT_CORPSE_SCORE + fear, "corpse present", f"fear {fear}")
        return ActionScore(0)

    def run(self, ctx: BrainContext) -> BrainResult:
        refresh_corpse_rot(ctx.state, ctx.now)
        for corpse in ctx.state.corpse_records:
            if corpse.get("folder_path") == str(ctx.folder) and not corpse.get("eaten"):
                corpse["seen"] = True
                ctx.state.memory["saw_dead_boogart"] = True
                return BrainResult(self.id, f"corpse:{corpse.get('rot_stage')}")
        return BrainResult(self.id, "corpse seen")


class GiveGiftAction(BrainAction):
    id = "give_gift"
    gift_names = ("soft_purr.txt", "shiny_string.gift", "small_thank_you.txt", "nap_place.txt")

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        if ctx.state.stage in {"newborn", "baby_kitten"}:
            return ActionScore(0)
        last_gift = ctx.state.memory.get("last_gift_at")
        if last_gift and ctx.now - _parse_datetime(str(last_gift)) < timedelta(hours=12):
            return ActionScore(0)
        trust = ctx.needs.get("trust", 0)
        return ActionScore.because(
            tuning.GIVE_GIFT_BASE_SCORE + ctx.state.affection * tuning.GIVE_GIFT_AFFECTION_WEIGHT + trust,
            "gift eligible",
            f"trust {trust}",
        )

    def run(self, ctx: BrainContext) -> BrainResult:
        rng = random.Random(f"{ctx.state.incarnation_id}:{ctx.now.date().isoformat()}:gift")
        name = rng.choice(self.gift_names)
        path = ctx.folder / name
        if not path.exists():
            ctx.fs.write_owned_text(ctx.state, path, "for you\n")
        else:
            track_generated_file(ctx.state, path)
        ctx.state.memory["last_gift_at"] = ctx.now.isoformat(timespec="seconds")
        return BrainResult(self.id, f"gift:{name}", path)


class RoamAction(BrainAction):
    id = "roam"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle != "alive":
            return ActionScore(0)
        if ctx.state.stage in {"newborn", "baby_kitten"}:
            return ActionScore(0)
        if ctx.place.hazard_count:
            return ActionScore(0)
        if ctx.state.memory.get("last_roam_at") and ctx.now - _parse_datetime(str(ctx.state.memory["last_roam_at"])) < timedelta(hours=1):
            return ActionScore(0)
        candidates = self._candidates(ctx)
        if not candidates:
            return ActionScore(0)
        room = choose_room(ctx, candidates)
        room_score = room.value if room else 0
        curiosity = ctx.needs.get("curiosity", 0)
        reasons = [f"roam targets: {len(candidates)}", f"room score {room_score}", f"curiosity {curiosity}"]
        if room:
            reasons.extend(room.reasons[:3])
        return ActionScore.because(tuning.ROAM_BASE_SCORE + ctx.state.hunger + curiosity + room_score, *reasons)

    def run(self, ctx: BrainContext) -> BrainResult:
        candidates = self._candidates(ctx)
        if not candidates:
            return BrainResult(self.id, "nowhere to go")

        room = choose_room(ctx, candidates)
        if room:
            destination = room.path
        else:
            rng = random.Random(f"{ctx.state.incarnation_id}:{ctx.now.isoformat(timespec='hours')}:roam")
            destination = rng.choice(candidates)
        old_sprite = ctx.folder / "boogart.png"
        if old_sprite.exists():
            ctx.fs.delete_owned(ctx.state, old_sprite)
        ctx.state.current_folder = str(destination)
        ctx.state.memory["last_roam_at"] = ctx.now.isoformat(timespec="seconds")
        remember_room_visit(ctx, destination)
        return BrainResult(self.id, f"moved to {destination.name}", destination)

    def _candidates(self, ctx: BrainContext) -> list[Path]:
        candidates: list[Path] = []
        for item in ctx.observations:
            if item.kind != "folder":
                continue
            if item.hazard or item.corpse:
                continue
            if item.name.startswith("."):
                continue
            if ctx.state.wander_scope == "marked" and not (item.path / ROOM_MARKER).exists():
                continue
            candidates.append(item.path)
        return candidates


class VocalizeAction(BrainAction):
    id = "vocalize"

    def score(self, ctx: BrainContext) -> ActionScore:
        if ctx.state.lifecycle == "alive":
            loneliness = ctx.needs.get("loneliness", 0)
            return ActionScore.because(tuning.VOCALIZE_SCORE + loneliness, "always vocalize", f"loneliness {loneliness}")
        return ActionScore(0)

    def run(self, ctx: BrainContext) -> BrainResult:
        return BrainResult(self.id, "mrrp")


DEFAULT_ACTIONS: tuple[BrainAction, ...] = (
    RebirthAction(),
    DieAction(),
    EatCorpseAction(),
    EatFoodAction(),
    AvoidHazardAction(),
    ReactToCorpseAction(),
    GiveGiftAction(),
    SeedDailyHazardAction(),
    RoamAction(),
    VocalizeAction(),
)


def food_score(name: str) -> int:
    lowered = name.lower()
    score = 10
    if any(word in lowered for word in ("fish", "milk", "chicken", "treat")):
        score += 20
    if any(word in lowered for word in ("battery", "glass", "wire", "dead_boogart")):
        score -= 30
    if "nothing" in lowered:
        score -= 10
    return score


def _parse_datetime(value: str):
    from boogart.core.growth import parse_timestamp

    return parse_timestamp(value)
