import json
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import ml_service, seed, simulator
from .config import FRONTEND_DIR, MODEL_DIR
from .database import SessionLocal, get_db
from .locations import CITIES
from .models import Bot, Detection, Transaction
from .websocket_manager import manager

app = FastAPI(title="Smart Fraud Detection System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_frontend_caching(request, call_next):
    response = await call_next(request)

    if request.url.path in ("/", "") or request.url.path.startswith(("/js/", "/css/")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

    return response


@app.on_event("startup")
def on_startup():
    seed.create_tables()

    db = SessionLocal()

    try:
        bots = seed.seed_bots(db)
        seed.seed_demo_history(db, bots)
        simulator.state.warm_cache(db)
    finally:
        db.close()

    try:
        ml_service.load_artifacts()
    except FileNotFoundError:
        print(
            "WARNING: trained model artifacts not found. "
            "Run ml/preprocess.py and ml/train_models.py first."
        )


def bot_to_dict(bot):
    return {
        "id": bot.id,
        "account_id": bot.account_id,
        "display_name": bot.display_name,
        "country": bot.country,
        "city": bot.city,
        "balance": bot.balance,
        "profile": bot.profile,
    }


def transaction_to_dict(transaction, db):
    sender = db.get(Bot, transaction.sender_id)
    receiver = db.get(Bot, transaction.receiver_id)
    detection = transaction.detection

    return {
        "id": transaction.id,
        "sender": sender.display_name if sender else None,
        "sender_account": sender.account_id if sender else None,
        "sender_id": transaction.sender_id,
        "receiver": receiver.display_name if receiver else None,
        "receiver_account": receiver.account_id if receiver else None,
        "receiver_id": transaction.receiver_id,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "origin": {
            "city": transaction.origin_city,
            "country": transaction.origin_country,
        },
        "destination": {
            "city": transaction.destination_city,
            "country": transaction.destination_country,
        },
        "status": transaction.status,
        "timestamp": transaction.timestamp.isoformat(),
        "rule_flagged": detection.rule_flagged if detection else None,
        "rule_reason": detection.rule_reason if detection else None,
        "model_name": detection.model_name if detection else None,
        "model_flagged": detection.model_flagged if detection else None,
        "model_probability": detection.model_probability if detection else None,
    }


@app.get("/api/locations")
def list_locations():
    return CITIES


@app.get("/api/bots")
def list_bots(db: Session = Depends(get_db)):
    return [bot_to_dict(bot) for bot in db.query(Bot).all()]


@app.get("/api/bots/{bot_id}")
def get_bot(bot_id: int, limit: int = 40, db: Session = Depends(get_db)):
    bot = db.get(Bot, bot_id)

    if not bot:
        return {"error": "bot not found"}

    history = (
        db.query(Transaction)
        .filter((Transaction.sender_id == bot_id) | (Transaction.receiver_id == bot_id))
        .order_by(Transaction.timestamp.desc())
        .limit(limit)
        .all()
    )

    sent_count = db.query(Transaction).filter(Transaction.sender_id == bot_id).count()

    received_count = (
        db.query(Transaction).filter(Transaction.receiver_id == bot_id).count()
    )

    flagged_count = (
        db.query(Transaction)
        .join(Detection, Detection.transaction_id == Transaction.id)
        .filter(
            Transaction.sender_id == bot_id,
            Detection.rule_flagged.is_(True),
        )
        .count()
    )

    return {
        **bot_to_dict(bot),
        "stats": {
            "sent": sent_count,
            "received": received_count,
            "flagged": flagged_count,
        },
        "transactions": [transaction_to_dict(t, db) for t in history],
    }


@app.get("/api/transactions")
def list_transactions(limit: int = 100, db: Session = Depends(get_db)):
    transactions = (
        db.query(Transaction).order_by(Transaction.timestamp.desc()).limit(limit).all()
    )

    return [transaction_to_dict(t, db) for t in transactions]


@app.get("/api/transactions/{transaction_id}")
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)

    if not transaction:
        return {"error": "not found"}

    return transaction_to_dict(transaction, db)


@app.get("/api/model-metrics")
def get_model_metrics():
    metrics_file = Path(MODEL_DIR).resolve() / "metrics.json"

    if not metrics_file.exists():
        return {"error": "metrics.json not found - run ml/train_models.py"}

    return json.loads(metrics_file.read_text())


@app.post("/api/simulator/run")
async def run_simulator(tps: float | None = None):
    simulator.start(tps)

    return {
        "running": True,
        "tps": simulator.state.tps,
    }


@app.post("/api/simulator/pause")
async def pause_simulator():
    await simulator.pause()

    return {"running": False}


@app.post("/api/simulator/reset")
async def reset_simulator(db: Session = Depends(get_db)):
    still_running = await simulator.reset(db)

    return {
        "running": still_running,
        "reset": True,
        "tps": simulator.state.tps,
    }


@app.get("/api/simulator/status")
def get_simulator_status():
    return {
        "running": simulator.state.running,
        "tps": simulator.state.tps,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)


app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)
