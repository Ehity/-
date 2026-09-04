"""Simple, explainable subscription detection."""

import pandas as pd

from service_normalizer import normalize_service_name


def _intervals_in_days(payments: pd.DataFrame) -> pd.Series:
    """Return payment intervals in days, including intervals shorter than one day."""
    return payments["date"].diff().dropna().dt.total_seconds() / 86_400


def _is_monthly_candidate(payments: pd.DataFrame, intervals: pd.Series) -> bool:
    """Check the mandatory conditions for a monthly-subscription candidate."""
    if len(payments) < 3 or intervals.empty:
        return False

    period_days = (payments["date"].iloc[-1] - payments["date"].iloc[0]).total_seconds() / 86_400
    median_interval = intervals.median()
    return period_days >= 50 and 25 <= median_interval <= 35


def _amounts_are_stable(payments: pd.DataFrame) -> bool:
    """Accept amounts whose maximum deviation from their middle is at most 10%."""
    amounts = payments["amount"].abs()
    middle_amount = (amounts.min() + amounts.max()) / 2
    if middle_amount == 0:
        return False
    maximum_deviation = (amounts - middle_amount).abs().max() / middle_amount
    return maximum_deviation <= 0.10


def _score_subscription(intervals: pd.Series, amounts_stable: bool) -> int:
    """Score a candidate after it has passed the monthly checks."""
    score = 25  # At least three payments, guaranteed by _is_monthly_candidate.
    score += 30 if intervals.between(25, 35).all() else 10
    if amounts_stable:
        score += 25
    return score + 20  # All payments belong to one normalized service group.


def find_subscriptions(df: pd.DataFrame) -> list[dict]:
    """Group payments by normalized service and calculate a deterministic score."""
    required_columns = {"date", "description", "amount"}
    if not required_columns.issubset(df.columns):
        raise ValueError("DataFrame должен содержать date, description и amount.")

    payments = df.loc[:, ["date", "description", "amount"]].copy()
    payments["date"] = pd.to_datetime(payments["date"], errors="coerce")
    payments["amount"] = pd.to_numeric(payments["amount"], errors="coerce")
    payments = payments.dropna(subset=["date", "description", "amount"])
    payments["service"] = payments["description"].map(normalize_service_name)
    payments = payments[payments["service"] != ""]

    subscriptions = []
    for service, group in payments.groupby("service", sort=True):
        ordered = group.sort_values("date").reset_index(drop=True)
        intervals = _intervals_in_days(ordered)
        if not _is_monthly_candidate(ordered, intervals):
            continue

        amounts_stable = _amounts_are_stable(ordered)
        intervals_are_monthly = intervals.between(25, 35).all()
        score = _score_subscription(intervals, amounts_stable)
        status = (
            "likely_subscription"
            if intervals_are_monthly and amounts_stable
            else "possible_subscription"
        )
        subscriptions.append(
            {
                "service": service,
                "service_raw": ordered.iloc[0]["description"],
                "payments_count": int(len(ordered)),
                "average_amount": round(float(ordered["amount"].abs().mean()), 2),
                "average_interval_days": round(float(intervals.mean()), 2),
                "score": score,
                "status": status,
            }
        )

    return subscriptions
