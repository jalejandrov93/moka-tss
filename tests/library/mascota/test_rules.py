# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tests for the declarative alert-rule engine (library/mascota/rules.py).
#
# No real clock and no real file I/O for the state-machine tests: time is
# injected via a manually-advanced fake clock and rule sets are built as
# plain dicts. A single test at the bottom loads the real
# res/mascota/rules.yaml default rule set to make sure it stays valid.

import math
import unittest
from pathlib import Path

from library.mascota.rules import RuleEngine, RulesConfigError

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = REPO_ROOT / "res" / "mascota" / "rules.yaml"

DEFAULT_MOODS = ["durmiendo", "calma", "atenta", "agobiada", "alarmada", "error"]


class _FakeClock:
    """A manually-advanced clock so hysteresis tests never call sleep()."""

    def __init__(self, start=0.0):
        self._now = start

    def __call__(self):
        return self._now

    def advance(self, seconds):
        self._now += seconds


def _engine(rules, moods=None, default_mood="calma", clock=None):
    config = {
        "moods": moods if moods is not None else list(DEFAULT_MOODS),
        "default_mood": default_mood,
        "rules": rules,
    }
    return RuleEngine.from_dict(config, clock=clock or _FakeClock())


class DefaultMoodTests(unittest.TestCase):
    def test_default_mood_when_no_rules_fire(self):
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85, "mood": "agobiada",
        }])
        self.assertEqual(engine.evaluate({"cpu": 10}), "calma")

    def test_default_mood_with_no_rules_at_all(self):
        engine = _engine([])
        self.assertEqual(engine.evaluate({"cpu": 999}), "calma")

    def test_default_mood_property(self):
        engine = _engine([], default_mood="durmiendo")
        self.assertEqual(engine.default_mood, "durmiendo")


class ForDebounceTests(unittest.TestCase):
    def test_does_not_fire_before_for_elapses(self):
        clock = _FakeClock()
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85,
            "for": 30, "mood": "agobiada",
        }], clock=clock)
        engine.evaluate({"cpu": 90})
        clock.advance(29)
        self.assertEqual(engine.evaluate({"cpu": 90}), "calma")

    def test_fires_once_for_elapses(self):
        clock = _FakeClock()
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85,
            "for": 30, "mood": "agobiada",
        }], clock=clock)
        engine.evaluate({"cpu": 90})
        clock.advance(30)
        self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")

    def test_for_timer_resets_if_condition_drops_before_elapsed(self):
        clock = _FakeClock()
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85,
            "for": 30, "mood": "agobiada",
        }], clock=clock)
        engine.evaluate({"cpu": 90})
        clock.advance(20)
        engine.evaluate({"cpu": 10})  # condition drops before firing: timer resets
        clock.advance(20)
        # Only 20s have elapsed since the metric went back above value.
        self.assertEqual(engine.evaluate({"cpu": 90}), "calma")

    def test_data_gap_during_active_for_timer_resets_it(self):
        # A missing/invalid reading in the middle of the debounce window
        # must not let the elapsed wall-clock time count toward `for`: only
        # two real high readings, 29s apart, must NOT be treated as 30s of
        # continuously-held condition.
        clock = _FakeClock()
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85,
            "for": 30, "mood": "agobiada",
        }], clock=clock)
        engine.evaluate({"cpu": 90})  # condition_since = 0
        clock.advance(1)
        engine.evaluate({})  # gap: frozen, no valid reading
        clock.advance(29)  # total elapsed since t=0 is now 30s
        # Resuming after a gap restarts the debounce: this must still read
        # "calma", not "agobiada" as if the condition held continuously.
        self.assertEqual(engine.evaluate({"cpu": 90}), "calma")
        clock.advance(30)
        self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")

    def test_clock_jump_backwards_restarts_the_timer_instead_of_freezing(self):
        # Decision: a clock that appears to move backwards relative to an
        # in-progress timer is treated like a data gap, not tolerated by
        # "waiting for the old value to be caught up to". The timer
        # restarts from the new (lower) `now`.
        clock = _FakeClock(start=50.0)
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85,
            "for": 10, "mood": "agobiada",
        }], clock=clock)
        engine.evaluate({"cpu": 90})  # condition_since = 50
        clock.advance(-30)  # now = 20: clock went backwards
        self.assertEqual(engine.evaluate({"cpu": 90}), "calma")  # restarted at 20
        clock.advance(10)  # now = 30: 10s since the restart at 20
        self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")


class HysteresisTests(unittest.TestCase):
    """release/release_for prevent flicker when a metric oscillates."""

    def _oscillating_engine(self):
        clock = _FakeClock()
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85,
            "for": 10, "release": 75, "release_for": 15, "mood": "agobiada",
        }], clock=clock)
        return engine, clock

    def test_release_lower_than_value_creates_dead_band(self):
        engine, clock = self._oscillating_engine()
        engine.evaluate({"cpu": 90})
        clock.advance(10)
        self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")
        # Oscillate between 80 (below value, above release) and 90: must
        # never clear, because it never drops below the release threshold.
        for _ in range(5):
            clock.advance(1)
            self.assertEqual(engine.evaluate({"cpu": 80}), "agobiada")
            clock.advance(1)
            self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")

    def test_clears_after_release_for_elapses_below_release_threshold(self):
        engine, clock = self._oscillating_engine()
        engine.evaluate({"cpu": 90})
        clock.advance(10)
        engine.evaluate({"cpu": 90})  # fired
        clock.advance(1)
        engine.evaluate({"cpu": 70})  # below release: starts release timer
        clock.advance(14)
        self.assertEqual(engine.evaluate({"cpu": 70}), "agobiada")  # only 14s
        clock.advance(1)
        self.assertEqual(engine.evaluate({"cpu": 70}), "calma")  # 15s elapsed

    def test_release_timer_resets_if_value_returns_above_release(self):
        engine, clock = self._oscillating_engine()
        engine.evaluate({"cpu": 90})
        clock.advance(10)
        engine.evaluate({"cpu": 90})
        clock.advance(1)
        engine.evaluate({"cpu": 70})  # start release timer
        clock.advance(10)
        engine.evaluate({"cpu": 80})  # back above release: resets release timer
        clock.advance(10)
        self.assertEqual(engine.evaluate({"cpu": 70}), "agobiada")  # only 0s since reset


class DefaultReleaseTests(unittest.TestCase):
    def test_default_release_equals_value_with_strict_inverse(self):
        clock = _FakeClock()
        engine = _engine([{
            "id": "cpu-alto", "metric": "cpu", "op": ">=", "value": 85, "mood": "agobiada",
        }], clock=clock)
        engine.evaluate({"cpu": 85})
        self.assertEqual(engine.evaluate({"cpu": 85}), "agobiada")  # for defaults to 0
        self.assertEqual(engine.evaluate({"cpu": 85}), "agobiada")  # exactly at threshold: stays
        self.assertEqual(engine.evaluate({"cpu": 84.999}), "calma")  # below: clears (release_for=0)


class PriorityResolutionTests(unittest.TestCase):
    def test_higher_priority_wins(self):
        engine = _engine([
            {"id": "cpu-atenta", "metric": "cpu", "op": ">=", "value": 50, "mood": "atenta", "priority": 10},
            {"id": "cpu-alarmada", "metric": "cpu", "op": ">=", "value": 50, "mood": "alarmada", "priority": 90},
        ])
        self.assertEqual(engine.evaluate({"cpu": 99}), "alarmada")

    def test_tie_break_by_mood_urgency_when_priority_ties(self):
        engine = _engine([
            {"id": "b-rule", "metric": "cpu", "op": ">=", "value": 50, "mood": "atenta", "priority": 50},
            {"id": "a-rule", "metric": "ram", "op": ">=", "value": 50, "mood": "alarmada", "priority": 50},
        ])
        self.assertEqual(engine.evaluate({"cpu": 99, "ram": 99}), "alarmada")

    def test_tie_break_by_rule_id_when_priority_and_mood_tie(self):
        engine = _engine([
            {"id": "zzz-rule", "metric": "cpu", "op": ">=", "value": 50, "mood": "atenta", "priority": 50},
            {"id": "aaa-rule", "metric": "ram", "op": ">=", "value": 50, "mood": "atenta", "priority": 50},
        ])
        result = engine.evaluate_detailed({"cpu": 99, "ram": 99})
        self.assertEqual(result.mood, "atenta")
        self.assertEqual(result.winning_rule_id, "aaa-rule")

    def test_tie_break_is_independent_of_declaration_order(self):
        # Same two rules, declared in the opposite order: the winner must
        # still be "aaa-rule" (id sort), never the dict/list insertion order.
        engine = _engine([
            {"id": "aaa-rule", "metric": "ram", "op": ">=", "value": 50, "mood": "atenta", "priority": 50},
            {"id": "zzz-rule", "metric": "cpu", "op": ">=", "value": 50, "mood": "atenta", "priority": 50},
        ])
        result = engine.evaluate_detailed({"cpu": 99, "ram": 99})
        self.assertEqual(result.winning_rule_id, "aaa-rule")


class MissingDataTests(unittest.TestCase):
    """Absent, None, and NaN metrics must never fire and never crash. A rule
    already fired on stale (now-missing) data must stay fired: missing data
    freezes that rule's state instead of clearing it."""

    def _rule(self, **overrides):
        rule = {"id": "r", "metric": "cpu", "op": ">=", "value": 50, "mood": "agobiada"}
        rule.update(overrides)
        return rule

    def test_missing_metric_does_not_fire(self):
        engine = _engine([self._rule()])
        self.assertEqual(engine.evaluate({}), "calma")

    def test_none_value_does_not_fire(self):
        engine = _engine([self._rule()])
        self.assertEqual(engine.evaluate({"cpu": None}), "calma")

    def test_nan_value_does_not_fire(self):
        engine = _engine([self._rule()])
        self.assertEqual(engine.evaluate({"cpu": math.nan}), "calma")

    def test_non_numeric_string_value_does_not_crash_and_does_not_fire(self):
        # Realistic: an adapter (e.g. codexbar) can hand back "N/A" when a
        # provider errors. evaluate() must never raise for this.
        engine = _engine([self._rule()])
        self.assertEqual(engine.evaluate({"cpu": "N/A"}), "calma")

    def test_bool_value_is_treated_as_missing_not_as_0_or_1(self):
        # bool is a subclass of int in Python: without an explicit guard,
        # True >= 0 and False >= 0 are both silently True. Use a threshold
        # of 0 so a numeric-coercion bug would visibly fire.
        engine = _engine([{"id": "r", "metric": "cpu", "op": ">=", "value": 0, "mood": "agobiada"}])
        self.assertEqual(engine.evaluate({"cpu": True}), "calma")
        self.assertEqual(engine.evaluate({"cpu": False}), "calma")

    def test_non_numeric_value_does_not_clear_already_fired_rule(self):
        clock = _FakeClock()
        engine = _engine([self._rule()], clock=clock)
        engine.evaluate({"cpu": 90})  # fires
        self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")
        self.assertEqual(engine.evaluate({"cpu": "unknown"}), "agobiada")
        self.assertEqual(engine.evaluate({"cpu": True}), "agobiada")

    def test_missing_metric_does_not_clear_already_fired_rule(self):
        clock = _FakeClock()
        engine = _engine([self._rule()], clock=clock)
        engine.evaluate({"cpu": 90})  # for defaults to 0: fires immediately
        self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")
        clock.advance(1000)  # a large gap with no readings at all
        self.assertEqual(engine.evaluate({}), "agobiada")
        self.assertEqual(engine.evaluate({"cpu": None}), "agobiada")
        self.assertEqual(engine.evaluate({"cpu": math.nan}), "agobiada")
        # Once real data returns, the rule still behaves normally.
        self.assertEqual(engine.evaluate({"cpu": 10}), "calma")

    def test_missing_metric_does_not_start_the_for_timer(self):
        clock = _FakeClock()
        engine = _engine([self._rule(**{"for": 10})], clock=clock)
        engine.evaluate({})  # nothing to observe yet
        clock.advance(20)
        engine.evaluate({"cpu": 90})  # condition first genuinely observed now
        clock.advance(9)
        self.assertEqual(engine.evaluate({"cpu": 90}), "calma")  # only 9s of real data
        clock.advance(1)
        self.assertEqual(engine.evaluate({"cpu": 90}), "agobiada")


class OperatorTests(unittest.TestCase):
    def test_all_supported_operators(self):
        cases = [
            (">=", 50, 50, True), (">=", 50, 49, False),
            (">", 50, 51, True), (">", 50, 50, False),
            ("<=", 50, 50, True), ("<=", 50, 51, False),
            ("<", 50, 49, True), ("<", 50, 50, False),
            ("==", 50, 50, True), ("==", 50, 51, False),
            ("!=", 50, 51, True), ("!=", 50, 50, False),
        ]
        for op, threshold, metric_value, should_fire in cases:
            with self.subTest(op=op, value=metric_value):
                engine = _engine([{
                    "id": "r", "metric": "x", "op": op, "value": threshold, "mood": "agobiada",
                }])
                expected = "agobiada" if should_fire else "calma"
                self.assertEqual(engine.evaluate({"x": metric_value}), expected)


class ValidationTests(unittest.TestCase):
    """Malformed configs must raise RulesConfigError naming the offending
    rule id and field, never a raw KeyError, and never crash at eval time."""

    def test_unknown_operator_rejected_at_load(self):
        with self.assertRaises(RulesConfigError) as ctx:
            _engine([{"id": "r", "metric": "cpu", "op": "~=", "value": 50, "mood": "agobiada"}])
        message = str(ctx.exception)
        self.assertIn("r", message)
        self.assertIn("op", message)

    def test_unknown_mood_rejected_at_load(self):
        with self.assertRaises(RulesConfigError) as ctx:
            _engine([{"id": "r", "metric": "cpu", "op": ">=", "value": 50, "mood": "furiosa"}])
        message = str(ctx.exception)
        self.assertIn("r", message)
        self.assertIn("mood", message)

    def test_missing_required_field_names_rule_and_field(self):
        with self.assertRaises(RulesConfigError) as ctx:
            _engine([{"id": "r", "metric": "cpu", "op": ">=", "mood": "agobiada"}])  # no value
        message = str(ctx.exception)
        self.assertIn("r", message)
        self.assertIn("value", message)

    def test_missing_rule_id_still_raises_a_named_error(self):
        with self.assertRaises(RulesConfigError):
            _engine([{"metric": "cpu", "op": ">=", "value": 50, "mood": "agobiada"}])

    def test_unknown_default_mood_rejected(self):
        with self.assertRaises(RulesConfigError):
            RuleEngine.from_dict({"moods": ["calma"], "default_mood": "nope", "rules": []})

    def test_duplicate_rule_id_rejected(self):
        with self.assertRaises(RulesConfigError):
            _engine([
                {"id": "dup", "metric": "cpu", "op": ">=", "value": 50, "mood": "agobiada"},
                {"id": "dup", "metric": "ram", "op": ">=", "value": 50, "mood": "atenta"},
            ])

    def test_missing_moods_list_rejected(self):
        with self.assertRaises(RulesConfigError):
            RuleEngine.from_dict({"default_mood": "calma", "rules": []})

    def test_missing_default_mood_rejected(self):
        with self.assertRaises(RulesConfigError):
            RuleEngine.from_dict({"moods": ["calma"], "rules": []})

    def test_negative_for_rejected(self):
        with self.assertRaises(RulesConfigError):
            _engine([{"id": "r", "metric": "cpu", "op": ">=", "value": 50, "for": -1, "mood": "agobiada"}])

    def test_negative_release_for_rejected(self):
        with self.assertRaises(RulesConfigError):
            _engine([{
                "id": "r", "metric": "cpu", "op": ">=", "value": 50,
                "release_for": -1, "mood": "agobiada",
            }])

    def test_release_above_value_rejected_for_high_direction_op(self):
        # op ">=": a release threshold above value means a reading (e.g. 87
        # for value=85/release=90) is simultaneously firing and releasing.
        with self.assertRaises(RulesConfigError) as ctx:
            _engine([{
                "id": "r", "metric": "cpu", "op": ">=", "value": 85,
                "release": 90, "mood": "agobiada",
            }])
        message = str(ctx.exception)
        self.assertIn("r", message)
        self.assertIn("release", message)
        self.assertIn("value", message)

    def test_release_below_value_rejected_for_low_direction_op(self):
        # op "<=": symmetric case, release must not be below value.
        with self.assertRaises(RulesConfigError):
            _engine([{
                "id": "r", "metric": "cpu", "op": "<=", "value": 50,
                "release": 40, "mood": "agobiada",
            }])


class DefaultRulesFileTests(unittest.TestCase):
    """The shipped res/mascota/rules.yaml must itself be a valid config."""

    def test_default_rules_file_loads_and_validates(self):
        engine = RuleEngine.from_yaml_file(DEFAULT_RULES_PATH)
        self.assertEqual(engine.evaluate({}), engine.default_mood)


if __name__ == "__main__":
    unittest.main()
