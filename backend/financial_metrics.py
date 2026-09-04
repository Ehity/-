"""Cost calculations for detected subscriptions."""


def calculate_subscription_costs(subscription: dict) -> dict:
    """Add monthly and annual cost based on the detected average payment."""
    monthly_cost = round(float(subscription["average_amount"]), 2)
    return {"monthly_cost": monthly_cost, "annual_cost": round(monthly_cost * 12, 2)}


def calculate_total_monthly_cost(subscriptions) -> float:
    """Return the rounded sum of monthly costs."""
    return round(sum(float(item["monthly_cost"]) for item in subscriptions), 2)


def calculate_total_annual_cost(subscriptions) -> float:
    """Return the rounded sum of annual costs."""
    return round(sum(float(item["annual_cost"]) for item in subscriptions), 2)
