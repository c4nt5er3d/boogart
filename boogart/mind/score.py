from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionScore:
    value: int
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return self.value > 0

    def __add__(self, other: int) -> ActionScore:
        return ActionScore(self.value + other, self.reasons)

    def __radd__(self, other: int) -> ActionScore:
        return ActionScore(self.value + other, self.reasons)

    @classmethod
    def because(cls, value: int, *reasons: str) -> ActionScore:
        return cls(value, tuple(reason for reason in reasons if reason))

    def with_reason(self, reason: str) -> ActionScore:
        if not reason:
            return self
        return ActionScore(self.value, self.reasons + (reason,))
