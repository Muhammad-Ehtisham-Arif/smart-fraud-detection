from collections import defaultdict
from datetime import datetime, timedelta, timezone

VELOCITY_WINDOW_SECONDS = 20
VELOCITY_MAX_COUNT = 10

HIGH_AMOUNT_MULTIPLIER = 6
HIGH_AMOUNT_ABSOLUTE_FLOOR = 250_000

MIN_HISTORY_FOR_LOCATION_RULE = 8

recent_transactions = defaultdict(list)


def check_balance(sender_balance: float, amount: float) -> tuple[bool, str | None]:
    if amount > sender_balance:
        return False, (
            f"Insufficient balance: balance={sender_balance:.2f}, "
            f"requested={amount:.2f}"
        )

    return True, None


def check_velocity(bot_account_id: str, now: datetime) -> str | None:
    history = recent_transactions[bot_account_id]

    cutoff = now - timedelta(seconds=VELOCITY_WINDOW_SECONDS)

    history = [time for time in history if time >= cutoff]
    history.append(now)

    recent_transactions[bot_account_id] = history

    if len(history) > VELOCITY_MAX_COUNT:
        return (
            f"Velocity rule triggered: {len(history)} transactions from "
            f"{bot_account_id} within {VELOCITY_WINDOW_SECONDS}s "
            f"(limit is {VELOCITY_MAX_COUNT})"
        )

    return None


def check_high_amount(amount: float, sender_avg_amount: float) -> str | None:
    if amount >= HIGH_AMOUNT_ABSOLUTE_FLOOR:
        return (
            f"High amount rule triggered: amount={amount:.2f} "
            f"exceeds absolute floor {HIGH_AMOUNT_ABSOLUTE_FLOOR}"
        )

    if sender_avg_amount > 0 and amount >= sender_avg_amount * HIGH_AMOUNT_MULTIPLIER:
        return (
            f"High amount rule triggered: amount={amount:.2f} is "
            f"{amount / sender_avg_amount:.1f}x this bot's average "
            f"({sender_avg_amount:.2f})"
        )

    return None


def check_unusual_location(
    destination_country: str, known_countries: set[str]
) -> str | None:

    if (
        len(known_countries) >= MIN_HISTORY_FOR_LOCATION_RULE
        and destination_country not in known_countries
    ):
        return (
            f"Unusual location rule triggered: {destination_country} "
            f"is not in this bot's known destination countries "
            f"{sorted(known_countries)}"
        )

    return None


def evaluate_transaction(
    *,
    bot_account_id: str,
    amount: float,
    sender_balance: float,
    sender_avg_amount: float,
    sender_known_countries: set[str],
    destination_country: str,
    now: datetime | None = None,
) -> dict:

    now = now or datetime.now(timezone.utc)

    sufficient, balance_reason = check_balance(sender_balance, amount)

    if not sufficient:
        return {"status": "FAILED", "flagged": False, "reason": balance_reason}

    reasons = [
        check_velocity(bot_account_id, now),
        check_high_amount(amount, sender_avg_amount),
        check_unusual_location(destination_country, sender_known_countries),
    ]

    reasons = [reason for reason in reasons if reason]

    if reasons:
        return {"status": "SUSPICIOUS", "flagged": True, "reason": "; ".join(reasons)}

    return {"status": "COMPLETED", "flagged": False, "reason": None}
