"""Entry point for Scaner MVP analysis."""

import json
import sys

from financial_metrics import (
    calculate_subscription_costs,
    calculate_total_annual_cost,
    calculate_total_monthly_cost,
)
from parser import parse_statement
from subscription_logic import find_subscriptions


def analyze_statement(file_path: str) -> dict:
    """Parse a statement, detect subscriptions and produce the frontend contract."""
    transactions = parse_statement(file_path)
    detected = find_subscriptions(transactions)

    subscriptions = []
    for item in detected:
        costs = calculate_subscription_costs(item)
        subscriptions.append(
            {
                "service": item["service"],
                "monthly_cost": costs["monthly_cost"],
                "annual_cost": costs["annual_cost"],
                "payments_count": item["payments_count"],
                "average_interval_days": item["average_interval_days"],
                "score": item["score"],
                "status": item["status"],
            }
        )

    return {
        "subscriptions": subscriptions,
        "summary": {
            "subscriptions_count": len(subscriptions),
            "total_monthly_cost": calculate_total_monthly_cost(subscriptions),
            "total_annual_cost": calculate_total_annual_cost(subscriptions),
        },
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование: python app.py path_to_statement.csv")
        raise SystemExit(1)
    print(json.dumps(analyze_statement(sys.argv[1]), ensure_ascii=False, indent=2))
