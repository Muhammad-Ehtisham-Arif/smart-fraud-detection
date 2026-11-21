from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from .database import Base


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True)
    account_id = Column(String(20), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    country = Column(String(60), nullable=False)
    city = Column(String(60), nullable=False)
    balance = Column(Float, nullable=False, default=0.0)
    profile = Column(String(30), nullable=False, default="regular")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sent_transactions = relationship(
        "Transaction", foreign_keys="Transaction.sender_id", back_populates="sender"
    )

    received_transactions = relationship(
        "Transaction", foreign_keys="Transaction.receiver_id", back_populates="receiver"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("bots.id"), nullable=False)

    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")

    origin_country = Column(String(60), nullable=False)
    origin_city = Column(String(60), nullable=False)

    destination_country = Column(String(60), nullable=False)
    destination_city = Column(String(60), nullable=False)

    status = Column(String(30), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sender = relationship(
        "Bot", foreign_keys=[sender_id], back_populates="sent_transactions"
    )

    receiver = relationship(
        "Bot", foreign_keys=[receiver_id], back_populates="received_transactions"
    )

    detection = relationship("Detection", uselist=False, back_populates="transaction")


class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True)
    transaction_id = Column(
        Integer, ForeignKey("transactions.id"), unique=True, nullable=False
    )

    rule_flagged = Column(Boolean, nullable=False, default=False)
    rule_reason = Column(String(500), nullable=True)

    model_name = Column(String(50), nullable=True)
    model_flagged = Column(Boolean, nullable=False, default=False)
    model_probability = Column(Float, nullable=True)

    final_status = Column(String(30), nullable=False)

    transaction = relationship("Transaction", back_populates="detection")
