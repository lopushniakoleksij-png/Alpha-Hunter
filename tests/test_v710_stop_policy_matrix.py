import unittest

from v710_stop_policy_matrix import (
    choose_policy,
)


def candidates():
    return [
        {
            "stop_source":
                "CURRENT_V78",

            "stop_pct":
                2.0,
        },
        {
            "stop_source":
                "15M_4",

            "stop_pct":
                0.8,
        },
        {
            "stop_source":
                "15M_12",

            "stop_pct":
                3.0,
        },
    ]


class TestPolicySelection(unittest.TestCase):
    def test_current_policy(self):
        result = choose_policy(
            "CURRENT_V78",
            candidates(),
        )

        self.assertEqual(
            result[
                "stop_source"
            ],
            "CURRENT_V78",
        )

    def test_tightest_policy(self):
        result = choose_policy(
            "TIGHTEST_5R",
            candidates(),
        )

        self.assertEqual(
            result[
                "stop_source"
            ],
            "15M_4",
        )

    def test_widest_policy(self):
        result = choose_policy(
            "WIDEST_5R",
            candidates(),
        )

        self.assertEqual(
            result[
                "stop_source"
            ],
            "15M_12",
        )

    def test_missing_fixed_policy(self):
        result = choose_policy(
            "15M_6",
            candidates(),
        )

        self.assertIsNone(
            result
        )


if __name__ == "__main__":
    unittest.main()
