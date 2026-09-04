"""Tests for the Scaner MVP backend."""

import os
import tempfile
import unittest

import pandas as pd

from app import analyze_statement
from financial_metrics import calculate_subscription_costs
from letter_generator import generate_unsubscribe_letter
from parser import parse_statement
from service_normalizer import normalize_service_name
from subscription_logic import find_subscriptions


class BackendTests(unittest.TestCase):
    def test_generates_nonempty_letter_for_netflix(self):
        self.assertTrue(generate_unsubscribe_letter("Netflix"))

    def test_letter_contains_service_name(self):
        service_name = "Яндекс Плюс"
        self.assertIn(service_name, generate_unsubscribe_letter(service_name))

    def test_letter_asks_to_cancel_subscription(self):
        letter = generate_unsubscribe_letter("VK Музыка")
        self.assertIn("отменить мою подписку", letter)

    def test_letter_rejects_empty_service_name(self):
        with self.assertRaises(ValueError):
            generate_unsubscribe_letter("")

    def test_letter_rejects_whitespace_service_name(self):
        with self.assertRaises(ValueError):
            generate_unsubscribe_letter("   ")

    def test_letter_rejects_none_service_name(self):
        with self.assertRaises(ValueError):
            generate_unsubscribe_letter(None)

    def test_ai_mode_uses_fallback_without_api(self):
        letter = generate_unsubscribe_letter("Netflix", use_ai=True)
        self.assertTrue(letter)
        self.assertIn("Netflix", letter)

    def test_normalizes_netflix(self):
        self.assertEqual(normalize_service_name("NETFLIX.COM*123"), "Netflix")

    def test_normalizes_youtube(self):
        self.assertEqual(normalize_service_name("GOOGLE*YOUTUBE"), "YouTube Premium")

    def test_empty_service_name(self):
        self.assertEqual(normalize_service_name(""), "")
        self.assertEqual(normalize_service_name(None), "")

    def test_monthly_netflix_payments_get_high_score(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2026-01-01", "2026-01-31", "2026-03-02", "2026-04-01", "2026-05-01"]
                ),
                "description": ["NETFLIX.COM*123"] * 5,
                "amount": [-799] * 5,
            }
        )
        subscription = find_subscriptions(frame)[0]
        self.assertGreaterEqual(subscription["score"], 70)
        self.assertEqual(subscription["status"], "likely_subscription")

    def test_irregular_payments_are_not_subscriptions(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-03-20", "2026-08-15"]),
                "description": ["NETFLIX.COM*123"] * 3,
                "amount": [-100, -300, -900],
            }
        )
        self.assertEqual(find_subscriptions(frame), [])

    def test_random_pyaterochka_purchases_are_not_subscriptions(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2026-01-01", "2026-01-04", "2026-01-08", "2026-01-16", "2026-01-19",
                     "2026-02-01", "2026-02-04", "2026-02-16", "2026-02-20", "2026-03-09"]
                ),
                "description": ["Пятёрочка"] * 10,
                "amount": [-450, -1200, -300, -750, -500, -900, -200, -1100, -350, -600],
            }
        )
        self.assertEqual(find_subscriptions(frame), [])

    def test_random_yandex_taxi_rides_are_not_subscriptions(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-09", "2026-01-22", "2026-01-24"]
                ),
                "description": ["Яндекс Такси"] * 6,
                "amount": [-320, -510, -280, -650, -410, -390],
            }
        )
        self.assertEqual(find_subscriptions(frame), [])

    def test_yandex_plus_payments_within_one_day_are_not_subscriptions(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2026-01-10 08:00", "2026-01-10 20:00", "2026-01-11 08:00"]
                ),
                "description": ["YANDEX*PLUS"] * 3,
                "amount": [-399] * 3,
            }
        )
        self.assertEqual(find_subscriptions(frame), [])

    def test_small_monthly_amount_change_is_still_subscription(self):
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-31", "2026-03-02"]),
                "description": ["MY SERVICE"] * 3,
                "amount": [-299, -299, -349],
            }
        )
        subscription = find_subscriptions(frame)[0]
        self.assertEqual(subscription["status"], "likely_subscription")

    def test_annual_cost(self):
        self.assertEqual(
            calculate_subscription_costs({"average_amount": 799})["annual_cost"], 9588.0
        )

    def test_analyze_statement_with_csv(self):
        content = (
            "Date,Description,Amount\n"
            "2026-01-10,NETFLIX.COM*123,-799\n"
            "2026-02-09,NETFLIX.COM*123,-799\n"
            "2026-03-11,NETFLIX.COM*123,-799\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as file:
            file.write(content)
            path = file.name
        try:
            result = analyze_statement(path)
        finally:
            os.unlink(path)

        self.assertEqual(result["summary"]["subscriptions_count"], 1)
        self.assertEqual(result["subscriptions"][0]["service"], "Netflix")
        self.assertEqual(result["summary"]["total_annual_cost"], 9588.0)

    def test_parses_sber_csv_column_names(self):
        content = (
            "Дата и время;Описание;Категория;Сумма (RUB);Остаток (RUB)\n"
            "10.01.2026 12:00:00;NETFLIX.COM*123;Развлечения;-799,00;1000,00\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as file:
            file.write(content)
            path = file.name
        try:
            result = parse_statement(path)
        finally:
            os.unlink(path)

        self.assertEqual(list(result.columns), ["date", "description", "amount"])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result["date"]))
        self.assertEqual(result.loc[0, "amount"], 799.0)


if __name__ == "__main__":
    unittest.main()
