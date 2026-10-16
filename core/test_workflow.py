import unittest

from core.textnorm import clean_identifier, to_ascii_digits
from core.workflow import (
    ACTIONS, APPROVED, CANCELLED, FINAL_STATUSES, REJECTED, SUBMITTED,
    SURVEY_VERIFIED, TRANSITIONS, InvalidTransition, RoleNotAllowed, next_status,
)


class WorkflowTests(unittest.TestCase):
    def test_happy_path(self):
        s = next_status(SUBMITTED, "survey_verify", "surveyor")
        self.assertEqual(s, SURVEY_VERIFIED)
        self.assertEqual(next_status(s, "approve", "ac_land"), APPROVED)

    def test_rejections_and_cancel(self):
        self.assertEqual(next_status(SUBMITTED, "survey_reject", "surveyor"), REJECTED)
        self.assertEqual(next_status(SURVEY_VERIFIED, "reject", "ac_land"), REJECTED)
        self.assertEqual(next_status(SUBMITTED, "cancel", "citizen"), CANCELLED)

    def test_cannot_skip_steps(self):
        with self.assertRaises(InvalidTransition):
            next_status(SUBMITTED, "approve", "ac_land")
        with self.assertRaises(InvalidTransition):
            next_status(SURVEY_VERIFIED, "survey_verify", "surveyor")
        with self.assertRaises(InvalidTransition):
            next_status(SURVEY_VERIFIED, "cancel", "citizen")

    def test_final_statuses_are_dead_ends(self):
        for status in FINAL_STATUSES:
            for action in ACTIONS:
                with self.assertRaises(InvalidTransition):
                    next_status(status, action, "ac_land")

    def test_wrong_role_denied_for_every_transition(self):
        roles = {"citizen", "surveyor", "ac_land", "lawyer", "admin"}
        for (status, action), (_, allowed) in TRANSITIONS.items():
            for role in roles - allowed:
                with self.assertRaises(RoleNotAllowed):
                    next_status(status, action, role)

    def test_unknown_action_rejected(self):
        with self.assertRaises(InvalidTransition):
            next_status(SUBMITTED, "delete_everything", "ac_land")


class TextNormTests(unittest.TestCase):
    def test_bengali_digits(self):
        self.assertEqual(to_ascii_digits("১২৪৫/১"), "1245/1")
        self.assertEqual(clean_identifier("  ১২৪৫  "), "1245")

    def test_empty(self):
        self.assertEqual(clean_identifier(""), "")
        self.assertEqual(clean_identifier(None), "")
        self.assertEqual(clean_identifier("   "), "")

    def test_rejects_dangerous_or_long_input(self):
        for bad in ("1' OR '1'='1", "12;DROP", "a" * 31, "<script>", "১২৩\n৪"):
            if "\n" in bad:
                self.assertEqual(clean_identifier(bad), "123 4")
                continue
            with self.assertRaises(ValueError):
                clean_identifier(bad)


if __name__ == "__main__":
    unittest.main()
