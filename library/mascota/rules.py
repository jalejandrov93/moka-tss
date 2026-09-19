# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays
# Mascota fork - declarative alert-rule engine
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Declarative alert-rule engine that turns raw metrics into a mascot mood.

Rules are loaded from a YAML file (see res/mascota/rules.yaml) so the user
can add or tune a rule by editing that file, never by editing this module.
This module never imports a sensor: metrics are handed to `evaluate()` as a
plain dict of name -> value by whatever caller owns the polling loop.

Hysteresis is the whole point: a metric oscillating around a threshold must
not make the mascot flicker between moods. Two independent debounces do
this:

- `for` (seconds): the condition must hold continuously for this long
  before the rule is considered fired.
- `release` / `release_for`: once fired, the rule stays fired until the
  metric crosses back past `release` (which may differ from `value`, to
  create a dead band) and stays there for `release_for` seconds.

Missing data policy (deliberate, see `RuleEngine._evaluate_rule`): a metric
that is absent from the dict, `None`, NaN, a non-numeric value (e.g. an
adapter handing back "N/A" when a provider errors), or a `bool` (a subclass
of `int` in Python, so `True`/`False` would otherwise silently compare as
1/0) freezes that rule's state for this tick. It never starts or advances
the `for` timer (so it cannot cause a fresh fire), and if the rule is
already fired it is left fired untouched (so a data gap never silently
clears an active alert on stale grounds). `evaluate()` never raises for any
of these: a caller polling every couple of seconds inside a render loop
must never be able to freeze it with one bad reading.

Once a real reading follows a gap, any timer already in progress for that
rule (`for` or `release_for`) is restarted from that tick's `now`, rather
than letting the wall-clock time spent in the gap silently count toward it:
two real high readings 30 seconds apart with nothing but gaps in between
must not be treated as 30 seconds of continuously-held condition. A clock
that appears to move backwards relative to an in-progress timer is treated
the same way (restarted from the new, lower `now`) instead of leaving the
timer frozen until the old clock value is caught up to.
"""

import math
import operator
import time
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional

import yaml

OPERATORS: Dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}

# The operator applied against `release` to decide the condition has eased
# enough to start the release timer. Chosen as the strict complement of the
# firing operator so a metric sitting exactly on the boundary never flickers
# even when the caller does not configure an explicit `release` value (see
# _build_rule, where release defaults to `value`).
RELEASE_OPERATORS: Dict[str, str] = {
    ">=": "<",
    ">": "<=",
    "<=": ">",
    "<": ">=",
    "==": "!=",
    "!=": "==",
}

# Ordering operators for which `release` has a required direction relative
# to `value` (see the "release above/below value" check in `_build_rule`).
# A HIGH-direction rule fires on a high reading, so its release threshold
# must not sit above `value` (a reading could otherwise be both firing and
# releasing at once). A LOW-direction rule is the mirror image. "==" and
# "!=" have no such numeric direction and are not checked.
HIGH_DIRECTION_OPS = frozenset({">=", ">"})
LOW_DIRECTION_OPS = frozenset({"<=", "<"})


class RulesConfigError(Exception):
    """Raised for a malformed rules config: always names the offending rule
    (by id, or its position when it has none) and the offending field, so
    callers never see a raw KeyError/TypeError from a typo in YAML."""


class Rule(NamedTuple):
    """One validated, immutable rule. Built only by `_build_rule`."""

    id: str
    metric: str
    op: str
    value: float
    for_seconds: float
    release: float
    release_for: float
    mood: str
    priority: float


class EvaluationResult(NamedTuple):
    """Full detail of one `evaluate()` tick, for tests and diagnostics."""

    mood: str
    winning_rule_id: Optional[str]
    fired_rule_ids: List[str]


class _RuleState:
    """Mutable per-rule hysteresis state, private to RuleEngine.

    `had_gap` marks that the most recent tick(s) had no usable reading for
    this rule (see `_is_missing`). It is consumed on the next tick that does
    carry a usable reading: any timer in progress is restarted from that
    tick's `now`, because continuity through the gap cannot be vouched for.
    """

    __slots__ = ("fired", "condition_since", "release_since", "had_gap")

    def __init__(self):
        self.fired = False
        self.condition_since: Optional[float] = None
        self.release_since: Optional[float] = None
        self.had_gap = False


def _is_missing(value) -> bool:
    """True for anything that is not a genuine numeric reading.

    Covers: None, NaN, non-numeric types (e.g. a string like "N/A" that an
    adapter hands back when a provider errors), and bool (a subclass of int
    in Python, so `True`/`False` would otherwise silently compare as 1/0).
    """
    if isinstance(value, bool):
        return True
    if not isinstance(value, (int, float)):
        return True
    return isinstance(value, float) and math.isnan(value)


def _rule_label(rule_dict: dict, index: int) -> str:
    rule_id = rule_dict.get("id") if isinstance(rule_dict, dict) else None
    if rule_id:
        return str(rule_id)
    return f"<rule at index {index}, no id>"


def _require_field(rule_dict: dict, field: str, label: str):
    if field not in rule_dict or rule_dict[field] in (None, ""):
        raise RulesConfigError(
            f"Rule '{label}' is missing required field '{field}'."
        )
    return rule_dict[field]


def _require_number(rule_dict: dict, field: str, label: str, default=None, minimum=None):
    if field not in rule_dict or rule_dict[field] is None:
        if default is None:
            raise RulesConfigError(
                f"Rule '{label}' is missing required numeric field '{field}'."
            )
        return default
    raw = rule_dict[field]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise RulesConfigError(
            f"Rule '{label}' has a non-numeric value for field '{field}': {raw!r}."
        )
    if minimum is not None and raw < minimum:
        raise RulesConfigError(
            f"Rule '{label}' has field '{field}' = {raw!r}, but it must be >= {minimum}."
        )
    return float(raw)


def _build_rule(rule_dict: dict, index: int, known_moods: List[str]) -> Rule:
    if not isinstance(rule_dict, dict):
        raise RulesConfigError(
            f"Rule at index {index} must be a mapping, got {type(rule_dict).__name__}."
        )
    label = _rule_label(rule_dict, index)

    rule_id = _require_field(rule_dict, "id", label)
    metric = _require_field(rule_dict, "metric", label)
    op = _require_field(rule_dict, "op", label)
    if op not in OPERATORS:
        allowed = ", ".join(sorted(OPERATORS))
        raise RulesConfigError(
            f"Rule '{label}' has unknown field 'op' = {op!r}. Allowed operators: {allowed}."
        )
    value = _require_number(rule_dict, "value", label)
    mood = _require_field(rule_dict, "mood", label)
    if mood not in known_moods:
        allowed = ", ".join(known_moods)
        raise RulesConfigError(
            f"Rule '{label}' has unknown field 'mood' = {mood!r}. Declared moods: {allowed}."
        )

    for_seconds = _require_number(rule_dict, "for", label, default=0.0, minimum=0)
    release = _require_number(rule_dict, "release", label, default=value)
    release_for = _require_number(rule_dict, "release_for", label, default=0.0, minimum=0)
    priority = _require_number(rule_dict, "priority", label, default=0.0)

    if op in HIGH_DIRECTION_OPS and release > value:
        raise RulesConfigError(
            f"Rule '{label}' has 'release' ({release!r}) greater than 'value' ({value!r}) "
            f"for op '{op}'. A release threshold above the firing threshold would let a "
            f"single reading be simultaneously firing and releasing. Set release <= value."
        )
    if op in LOW_DIRECTION_OPS and release < value:
        raise RulesConfigError(
            f"Rule '{label}' has 'release' ({release!r}) less than 'value' ({value!r}) "
            f"for op '{op}'. A release threshold below the firing threshold would let a "
            f"single reading be simultaneously firing and releasing. Set release >= value."
        )

    return Rule(
        id=str(rule_id),
        metric=str(metric),
        op=op,
        value=value,
        for_seconds=for_seconds,
        release=release,
        release_for=release_for,
        mood=mood,
        priority=priority,
    )


def _validate_config(config: dict):
    if not isinstance(config, dict):
        raise RulesConfigError(f"Rules config must be a mapping, got {type(config).__name__}.")

    moods = config.get("moods")
    if not isinstance(moods, list) or not moods:
        raise RulesConfigError("Rules config is missing a non-empty top-level 'moods' list.")

    default_mood = config.get("default_mood")
    if not default_mood or default_mood not in moods:
        raise RulesConfigError(
            f"Rules config 'default_mood' = {default_mood!r} must be one of the declared "
            f"'moods': {', '.join(moods)}."
        )

    raw_rules = config.get("rules") or []
    if not isinstance(raw_rules, list):
        raise RulesConfigError("Rules config 'rules' must be a list.")

    rules: List[Rule] = []
    seen_ids = set()
    for index, raw_rule in enumerate(raw_rules):
        rule = _build_rule(raw_rule, index, moods)
        if rule.id in seen_ids:
            raise RulesConfigError(f"Duplicate rule id '{rule.id}': rule ids must be unique.")
        seen_ids.add(rule.id)
        rules.append(rule)

    return moods, default_mood, rules


class RuleEngine:
    """Resolves exactly one active mood from a metrics dict on every tick.

    Tie-break rule (documented here per the design contract, exercised by
    ValidationTests/PriorityResolutionTests in test_rules.py): among rules
    fired at the same instant, the highest `priority` wins; on an exact
    priority tie, the more urgent mood wins (by position in the `moods`
    list, later = more urgent); if still tied, the rule whose `id` sorts
    first (plain string comparison) wins. This is computed by sorting on an
    explicit key tuple, never by dict/list iteration order, so the result
    never depends on declaration order.
    """

    def __init__(self, moods: List[str], default_mood: str, rules: List[Rule],
                 clock: Callable[[], float] = time.monotonic):
        self._moods = moods
        self._mood_rank = {mood: rank for rank, mood in enumerate(moods)}
        self._default_mood = default_mood
        self._rules = rules
        self._clock = clock
        self._states: Dict[str, _RuleState] = {rule.id: _RuleState() for rule in rules}

    @property
    def default_mood(self) -> str:
        return self._default_mood

    @classmethod
    def from_dict(cls, config: dict, clock: Callable[[], float] = time.monotonic) -> "RuleEngine":
        moods, default_mood, rules = _validate_config(config)
        return cls(moods, default_mood, rules, clock=clock)

    @classmethod
    def from_yaml_file(cls, path, clock: Callable[[], float] = time.monotonic) -> "RuleEngine":
        with open(Path(path), "r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        return cls.from_dict(config, clock=clock)

    def evaluate(self, metrics: dict) -> str:
        return self.evaluate_detailed(metrics).mood

    def evaluate_detailed(self, metrics: dict) -> EvaluationResult:
        now = self._clock()
        fired_ids: List[str] = []
        for rule in self._rules:
            if self._evaluate_rule(rule, metrics, now):
                fired_ids.append(rule.id)

        if not fired_ids:
            return EvaluationResult(mood=self._default_mood, winning_rule_id=None, fired_rule_ids=[])

        winner = min(
            fired_ids,
            key=lambda rule_id: self._rank_for(rule_id),
        )
        winning_rule = self._rule_by_id(winner)
        return EvaluationResult(mood=winning_rule.mood, winning_rule_id=winner, fired_rule_ids=fired_ids)

    def _rank_for(self, rule_id: str):
        rule = self._rule_by_id(rule_id)
        return (-rule.priority, -self._mood_rank[rule.mood], rule.id)

    def _rule_by_id(self, rule_id: str) -> Rule:
        for rule in self._rules:
            if rule.id == rule_id:
                return rule
        raise KeyError(rule_id)  # unreachable: fired_ids only ever contains known rule ids

    def _evaluate_rule(self, rule: Rule, metrics: dict, now: float) -> bool:
        state = self._states[rule.id]
        value = metrics.get(rule.metric)
        if _is_missing(value):
            # Deliberate freeze: never start/advance the `for` timer (so a
            # gap cannot cause a fresh fire) and never clear an already
            # fired rule on stale grounds. Just report its current state,
            # and remember that whatever timer resumes next cannot vouch
            # for continuity through this gap.
            state.had_gap = True
            return state.fired

        if state.had_gap:
            # A real reading follows a gap: discard any partially-elapsed
            # timer rather than let the gap's wall-clock time count toward
            # it (see module docstring, "Hysteresis"). The same restart
            # applies to a clock that jumped backwards, handled below by
            # the `now < ...since` checks.
            state.condition_since = None
            state.release_since = None
            state.had_gap = False

        condition_op = OPERATORS[rule.op]
        if not state.fired:
            if condition_op(value, rule.value):
                if state.condition_since is None or now < state.condition_since:
                    state.condition_since = now
                if now - state.condition_since >= rule.for_seconds:
                    state.fired = True
                    state.release_since = None
            else:
                state.condition_since = None
        else:
            release_op = OPERATORS[RELEASE_OPERATORS[rule.op]]
            if release_op(value, rule.release):
                if state.release_since is None or now < state.release_since:
                    state.release_since = now
                if now - state.release_since >= rule.release_for:
                    state.fired = False
                    state.condition_since = None
                    state.release_since = None
            else:
                state.release_since = None

        return state.fired
