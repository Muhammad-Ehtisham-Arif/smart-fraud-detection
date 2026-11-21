import random
from datetime import datetime, timedelta, timezone

from . import rule_engine
from .database import Base, SessionLocal, engine
from .locations import CITIES
from .models import Bot, Detection, Transaction

BOTS = [
    ("Alpha Traders Ltd", "high_roller"),
    ("Nova Retail Co", "regular"),
    ("Quantum Exports", "regular"),
    ("Silverline Holdings", "high_roller"),
    ("Dormant Capital", "dormant"),
    ("BlueWave Imports", "regular"),
    ("Pinnacle Finance", "high_roller"),
    ("Everyday Groceries Inc", "regular"),
    ("Orion Logistics", "regular"),
    ("Crescent Textiles", "regular"),
    ("Summit Petroleum", "high_roller"),
    ("Harbour Freight Co", "regular"),
    ("Vertex Pharma", "regular"),
    ("Golden Oak Bank", "high_roller"),
    ("Riverstone Mining", "high_roller"),
    ("Lantern Media Group", "regular"),
    ("Pacific Seafoods", "regular"),
    ("Ironclad Security", "regular"),
    ("Evergreen Agro", "regular"),
    ("Starlight Travel", "regular"),
    ("Mariner Shipping", "regular"),
    ("Quiet Trust Fund", "dormant"),
]


STARTING_BALANCE_RANGE = {
    "high_roller": (500_000, 2_000_000),
    "regular": (5_000, 50_000),
    "dormant": (100, 2_000),
}

DEMO_AMOUNT_RANGE = {
    "high_roller": (20_000, 150_000),
    "regular": (100, 8_000),
    "dormant": (50, 800),
}

DEMO_HISTORY_COUNT = 40


def create_tables():
    Base.metadata.create_all(bind=engine)


def seed_bots(db):
    if db.query(Bot).count() > 0:
        return db.query(Bot).all()

    bots = []

    for index, (name, profile) in enumerate(BOTS):
        city = CITIES[index % len(CITIES)]
        low, high = STARTING_BALANCE_RANGE[profile]

        bot = Bot(
            account_id=f"ACC{1000 + index}",
            display_name=name,
            country=city["country"],
            city=city["city"],
            balance=round(random.uniform(low, high), 2),
            profile=profile,
        )

        db.add(bot)
        bots.append(bot)

    db.commit()

    return bots


def seed_demo_history(db, bots, count=DEMO_HISTORY_COUNT, force=False):
    if not force and db.query(Transaction).count() > 0:
        return

    now = datetime.now(timezone.utc)

    for _ in range(count):
        sender, receiver = random.sample(bots, 2)

        low, high = DEMO_AMOUNT_RANGE.get(sender.profile, (100, 5_000))

        amount = round(random.uniform(low, high), 2)
        timestamp = now - timedelta(minutes=random.uniform(1, 120))

        rule_result = rule_engine.evaluate_transaction(
            bot_account_id=sender.account_id,
            amount=amount,
            sender_balance=sender.balance + amount,
            sender_avg_amount=(low + high) / 2,
            sender_known_countries={sender.country},
            destination_country=receiver.country,
            now=timestamp,
        )

        transaction = Transaction(
            sender_id=sender.id,
            receiver_id=receiver.id,
            amount=amount,
            currency="USD",
            origin_country=sender.country,
            origin_city=sender.city,
            destination_country=receiver.country,
            destination_city=receiver.city,
            status=rule_result["status"],
            timestamp=timestamp,
        )

        db.add(transaction)
        db.flush()

        db.add(
            Detection(
                transaction_id=transaction.id,
                rule_flagged=rule_result["flagged"],
                rule_reason=rule_result["reason"],
                model_name=None,
                model_flagged=False,
                model_probability=None,
                final_status=rule_result["status"],
            )
        )

    db.commit()


def main():
    create_tables()

    db = SessionLocal()

    try:
        bots = seed_bots(db)
        seed_demo_history(db, bots)

        print(f"Seeded {len(bots)} bots and demo transaction history.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
