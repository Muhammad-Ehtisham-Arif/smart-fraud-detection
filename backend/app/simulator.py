import asyncio
import random
import time
import traceback

from collections import defaultdict
from datetime import datetime, timezone

from . import ml_service, rule_engine, seed
from .config import DEFAULT_TPS
from .database import SessionLocal
from .models import Bot, Detection, Transaction
from .websocket_manager import manager

WARM_CACHE_LIMIT = 500

SUSPICIOUS_PATTERN_RATE = 0.05
INSUFFICIENT_BALANCE_RATE = 0.03

TYPICAL_AMOUNT_RANGE = {
    "high_roller": (20_000, 150_000),
    "regular": (100, 8_000),
    "dormant": (50, 800),
}

DEFAULT_AMOUNT_RANGE = (100, 5_000)

REGULAR_PARTNER_COUNT = 5
NEW_PARTNER_RATE = 0.12
BASELINE_PRIOR_WEIGHT = 5

MIN_SENDER_BALANCE = 500

BURST_SHARE_OF_ANOMALIES = 0.4
BURST_LENGTH_RANGE = (10, 14)


class SimulatorState:
    def __init__(self):
        self.running = False
        self.tps = DEFAULT_TPS
        self.task = None

        self.bot_average_amount = defaultdict(lambda: 1000.0)
        self.bot_transaction_count = defaultdict(int)
        self.bot_known_countries = defaultdict(set)
        self.bot_partners = {}

        self.burst_sender_id = None
        self.burst_remaining = 0

    def warm_cache(self, db):
        self.bot_average_amount.clear()
        self.bot_transaction_count.clear()
        self.bot_known_countries.clear()
        self.bot_partners.clear()

        bots = db.query(Bot).all()

        self.set_starting_profiles(bots)
        self.assign_regular_partners(bots)
        self.replay_recent_transactions(db)

    def set_starting_profiles(self, bots):
        for bot in bots:
            low, high = TYPICAL_AMOUNT_RANGE.get(bot.profile, DEFAULT_AMOUNT_RANGE)

            self.bot_average_amount[bot.account_id] = (low + high) / 2
            self.bot_transaction_count[bot.account_id] = BASELINE_PRIOR_WEIGHT
            self.bot_known_countries[bot.account_id].add(bot.country)

    def assign_regular_partners(self, bots):
        partner_picker = random.Random(42)
        bots_by_id = {bot.id: bot for bot in bots}

        for bot in bots:
            other_ids = [other.id for other in bots if other.id != bot.id]

            partner_ids = partner_picker.sample(
                other_ids, min(REGULAR_PARTNER_COUNT, len(other_ids))
            )

            self.bot_partners[bot.id] = partner_ids

            for partner_id in partner_ids:
                partner = bots_by_id[partner_id]
                self.bot_known_countries[bot.account_id].add(partner.country)

    def replay_recent_transactions(self, db):
        rows = (
            db.query(
                Bot.account_id, Transaction.amount, Transaction.destination_country
            )
            .join(Transaction, Transaction.sender_id == Bot.id)
            .order_by(Transaction.id.desc())
            .limit(WARM_CACHE_LIMIT)
            .all()
        )

        for account_id, amount, destination_country in rows:
            self.record_transaction(account_id, amount, destination_country)

    def record_transaction(self, account_id, amount, destination_country):
        count = self.bot_transaction_count[account_id]

        self.bot_average_amount[account_id] = (
            self.bot_average_amount[account_id] * count + amount
        ) / (count + 1)

        self.bot_transaction_count[account_id] = count + 1
        self.bot_known_countries[account_id].add(destination_country)


state = SimulatorState()


def choose_sender_and_receiver(bots):
    bots_by_id = {bot.id: bot for bot in bots}

    if state.burst_remaining > 0 and state.burst_sender_id in bots_by_id:
        state.burst_remaining -= 1
        sender = bots_by_id[state.burst_sender_id]

    else:
        affordable = [bot for bot in bots if bot.balance >= MIN_SENDER_BALANCE]

        sender = random.choice(affordable or bots)

    partners = [
        bots_by_id[partner_id]
        for partner_id in state.bot_partners.get(sender.id, [])
        if partner_id in bots_by_id
    ]

    if partners and random.random() > NEW_PARTNER_RATE:
        return sender, random.choice(partners)

    return sender, random.choice([bot for bot in bots if bot.id != sender.id])


def choose_amount(sender, average_amount, is_suspicious):
    if is_suspicious:
        return round(average_amount * random.uniform(8, 20), 2)

    low, high = TYPICAL_AMOUNT_RANGE.get(sender.profile, DEFAULT_AMOUNT_RANGE)

    amount = random.uniform(low, high)
    amount = min(amount, sender.balance * 0.6)

    return round(max(min(amount, sender.balance), 1.0), 2)


def decide_final_status(rule_result, ml_result):
    if rule_result["status"] == "FAILED":
        return "FAILED"

    if rule_result["flagged"] or ml_result["flagged"]:
        return "SUSPICIOUS"

    return "COMPLETED"


def build_payload(transaction, sender, receiver, rule_result, ml_result):
    return {
        "type": "transaction",
        "transaction": {
            "id": transaction.id,
            "sender": sender.display_name,
            "sender_account": sender.account_id,
            "receiver": receiver.display_name,
            "receiver_account": receiver.account_id,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "origin": {"city": sender.city, "country": sender.country},
            "destination": {"city": receiver.city, "country": receiver.country},
            "status": transaction.status,
            "timestamp": transaction.timestamp.isoformat(),
            "rule_flagged": rule_result["flagged"],
            "rule_reason": rule_result["reason"],
            "model_name": ml_result["model_name"],
            "model_flagged": ml_result["flagged"],
            "model_probability": ml_result["probability"],
        },
        "sender_balance": sender.balance,
        "receiver_balance": receiver.balance,
    }


def create_transaction():
    db = SessionLocal()

    try:
        bots = db.query(Bot).all()

        if len(bots) < 2:
            return None

        sender, receiver = choose_sender_and_receiver(bots)

        is_suspicious = random.random() < SUSPICIOUS_PATTERN_RATE

        if (
            is_suspicious
            and state.burst_remaining == 0
            and random.random() < BURST_SHARE_OF_ANOMALIES
        ):
            state.burst_sender_id = sender.id
            state.burst_remaining = random.randint(*BURST_LENGTH_RANGE)

        average_amount = state.bot_average_amount[sender.account_id]

        amount = choose_amount(sender, average_amount, is_suspicious)

        if random.random() < INSUFFICIENT_BALANCE_RATE:
            amount = round(sender.balance + random.uniform(100, 5000), 2)

        rule_result = rule_engine.evaluate_transaction(
            bot_account_id=sender.account_id,
            amount=amount,
            sender_balance=sender.balance,
            sender_avg_amount=average_amount,
            sender_known_countries=state.bot_known_countries[sender.account_id],
            destination_country=receiver.country,
        )

        ml_result = ml_service.predict(
            amount=amount,
            time_value=time.time(),
            fraud_pattern=is_suspicious,
        )

        status = decide_final_status(rule_result, ml_result)

        if status != "FAILED":
            sender.balance -= amount
            receiver.balance += amount

            state.record_transaction(sender.account_id, amount, receiver.country)

        transaction = Transaction(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=amount,
            currency="USD",
            origin_country=sender.country,
            origin_city=sender.city,
            destination_country=receiver.country,
            destination_city=receiver.city,
            status=status,
            timestamp=datetime.now(timezone.utc),
        )

        db.add(transaction)
        db.flush()

        db.add(
            Detection(
                transaction_id=transaction.id,
                rule_flagged=rule_result["flagged"],
                rule_reason=rule_result["reason"],
                model_name=ml_result["model_name"],
                model_flagged=ml_result["flagged"],
                model_probability=ml_result["probability"],
                final_status=status,
            )
        )

        db.commit()

        return build_payload(transaction, sender, receiver, rule_result, ml_result)

    finally:
        db.close()


async def run_loop():
    while state.running:
        started_at = time.monotonic()

        try:
            payload = await asyncio.to_thread(create_transaction)

            if payload:
                await manager.broadcast(payload)

        except Exception:
            traceback.print_exc()

        interval = 1.0 / state.tps if state.tps > 0 else 1.0

        await asyncio.sleep(max(0.0, interval - (time.monotonic() - started_at)))


def start(tps=None):
    if tps is not None:
        state.tps = tps

    if state.running and state.task and not state.task.done():
        return

    state.running = True
    state.task = asyncio.create_task(run_loop())


async def pause():
    state.running = False

    task = state.task
    state.task = None

    if task:
        await task


async def reset(db):
    was_running = state.running

    await pause()

    db.query(Detection).delete()
    db.query(Transaction).delete()
    db.commit()

    bots = db.query(Bot).all()

    seed.seed_demo_history(db, bots, force=True)
    state.warm_cache(db)

    if was_running:
        start()

    return was_running
