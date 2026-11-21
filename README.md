# Smart Fraud Detection System

An Artificial Intelligence course project (3rd semester) built around one question:

> **Machine Learning vs. Traditional Programming — how differently do they solve the same problem?**

Every simulated bank transaction in this app is judged **twice, independently**:

1. **Traditional Programming** — a human-written `if/else` rule engine. Every decision traces
   back to a line of code someone deliberately wrote.
2. **Machine Learning** — a model that *learned its own decision boundary* from ~285,000 real
   historical transactions, without anyone writing the rules.

The two verdicts are stored and displayed separately, and **they are allowed to disagree** —
that disagreement is the most interesting part of the demo.

The dashboard (3D globe + live feed) exists to *demonstrate* the comparison. The graded
substance is the ML pipeline: preprocessing, training, evaluation, and how predictions are used.

---

## Table of contents

1. [Quick start](#1-quick-start)
2. [The two decision systems](#2-the-two-decision-systems)
3. [The dataset](#3-the-dataset)
4. [The ML pipeline](#4-the-ml-pipeline)
5. [Model results](#5-model-results)
6. [The simulation](#6-the-simulation)
7. [Architecture and request flow](#7-architecture-and-request-flow)
8. [Project structure](#8-project-structure)
9. [API reference](#9-api-reference)
10. [Database schema](#10-database-schema)
11. [Configuration](#11-configuration)
12. [Design decisions worth knowing](#12-design-decisions-worth-knowing)
13. [Scope and limitations](#13-scope-and-limitations)

---

## 1. Quick start

### Prerequisites
- Python 3.11+
- PostgreSQL running locally

### One-time setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set your PostgreSQL password, then create the database:

```bash
psql -U postgres -c "CREATE DATABASE fraud_detection;"
```

Train the models (the dataset is already in `ml/data/raw/`):

```bash
python ml/preprocess.py
python ml/train_models.py
```

### Run

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** and press **Run**.

Tables are created and bots are seeded automatically on first startup — no migration step.

### Controls
| Control | Effect |
|---|---|
| **Run** | Starts generating transactions at the configured rate |
| **Pause** | Stops generation; in-flight work is allowed to finish |
| **Reset** | Clears all history, reseeds demo data, and **keeps running** if it was running |
| **Rate** | Transactions per second (default 3) |

---

## 2. The two decision systems

|  | Traditional Programming | Machine Learning |
|---|---|---|
| File | `backend/app/rule_engine.py` | `ml/train_models.py` + `backend/app/ml_service.py` |
| How it decides | Explicit rules a human wrote | A boundary learned from historical data |
| Inputs it sees | Balance, amount, bot's own history, destination country, velocity | `Time`, `Amount`, `V1`–`V28` |
| Output | `FAILED` / flagged + exact reason / clear | Flagged (0/1) + probability |
| Changes over time? | Only when a developer edits the code | Could be retrained on new data |
| Explainable? | Completely — it names the rule | Only as a probability |

### The rules (traditional side)

Evaluated in a fixed order. The hard constraint is checked first, then the "this looks
suspicious" rules:

| Rule | Condition | Outcome |
|---|---|---|
| **Balance validation** | `amount > balance` | `FAILED` — no funds move |
| **Velocity** | More than 10 transactions from one account in 20s | Suspicious |
| **High amount** | ≥ 6× the bot's own average, or ≥ $250,000 | Suspicious |
| **Unusual location** | Destination country never seen before for that bot | Suspicious |

Thresholds are deliberately conservative. In a real fraud system alerts must stay rare,
otherwise analysts drown in false positives — so a normal bot sits well under every limit and
only genuine outliers trip a rule. The high-amount rule is **relative to each bot's own
average**, because a $100,000 transfer is routine for a large company and alarming for a
corner shop.

The unusual-location rule only activates once a bot has sent to at least 8 distinct countries.
Before that it has no established pattern, so flagging it would produce noise rather than
signal.

### Outcome categories

These are kept strictly separate:

- **`FAILED`** — rejected by account validation (insufficient balance). Not fraud; no funds move.
- **`SUSPICIOUS`** — flagged by the rule engine and/or the ML model. An **alert for review**,
  not proof of a crime. The UI always shows *which* system raised it.
- **`COMPLETED`** — passed validation and was not flagged.

---

## 3. The dataset

| | |
|---|---|
| **Name** | Credit Card Fraud Detection |
| **Source** | ULB Machine Learning Group / Worldline — https://www.kaggle.com/mlg-ulb/creditcardfraud |
| **License** | Open Database License (ODbL) — free for research and education |
| **Size** | 284,807 real anonymised European card transactions (September 2013) |
| **Fraud cases** | 492 (**0.173%**) — severely imbalanced |
| **Columns** | `Time`, `Amount`, `V1`–`V28`, `Class` (1 = fraud) |

`V1`–`V28` are **PCA components**. The original bank could not release real feature names for
privacy reasons, so the data was transformed before publication. This is why the model's inputs
look abstract.

### A limitation we did not hide

This dataset contains **no city, country, or account-identity fields**. So the trained model can
only ever be shown `Time` / `Amount` / `V1`–`V28`-shaped input. Geography and velocity are used
**only by the rule engine**.

That is not a flaw in the demo — it mirrors reality, where different detection systems see
overlapping but non-identical information, and it is precisely why the two systems can reach
different conclusions about the same transaction.

#### The ML adapter

Simulated transactions have a real amount and timestamp but obviously have no PCA components.
`build_feature_row()` in `ml_service.py` constructs a valid model input by:

1. Placing the real `Time` and `Amount` in their trained column positions and scaling them with
   the **saved scalers from training**.
2. Sampling `V1`–`V28` from the per-class mean/std measured on the **training set only**
   (saved to `v_feature_stats.joblib` during preprocessing).

The simulator never pretends to know the real PCA values. This is a documented adapter, not a
claim about the data.

---

## 4. The ML pipeline

### Step 1 — Preprocessing (`ml/preprocess.py`)

1. Load the raw CSV and report the exact class balance.
2. **Stratified** 80/20 train/test split, preserving the 0.173% fraud ratio in both halves.
   Without stratification, random chance could put most fraud cases on one side.
3. Scale `Time` and `Amount` with `StandardScaler`. `V1`–`V28` are already PCA components on a
   comparable scale and are left alone.
4. Save the scalers, the exact feature column order, and the per-class V-statistics.

**No data leakage.** The scaler is `fit` on the training set only, then `transform`-ed (never
re-fit) on the test set and later on live transactions. Fitting on all the data first would let
test-set information influence training and inflate the scores.

### Step 2 — Training (`ml/train_models.py`)

Three beginner-friendly classifiers, all trained on the same data:

| Model | Why it's here |
|---|---|
| **Logistic Regression** | Simple linear baseline |
| **Decision Tree** (`max_depth=8`) | Non-linear, human-readable splits |
| **MLPClassifier** (one hidden layer, 16 units) | A minimal neural network — not deep learning |

Logistic Regression and the Decision Tree use `class_weight="balanced"` to cope with the extreme
imbalance, rather than a more complex resampling technique.

### Step 3 — Evaluation

Every model is scored on the **same held-out test set it has never seen**, reporting Accuracy,
Precision, Recall, F1 and a Confusion Matrix. Results are written to `ml/models/metrics.json`
and shown live in the dashboard's **Models** tab. **Nothing is hardcoded.**

---

## 5. Model results

From the last training run (see `ml/models/metrics.json` for current values):

| Model | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| Logistic Regression | 0.976 | 0.061 | 0.918 | 0.114 |
| Decision Tree | 0.981 | 0.069 | 0.827 | 0.128 |
| **MLP (small ANN)** | **0.999** | **0.833** | **0.816** | **0.825** |

### Why accuracy is the wrong metric here

A model that predicts "never fraud" for every single transaction scores **99.83% accuracy** on
this dataset, while catching zero fraud. Accuracy is meaningless on severely imbalanced data.

The honest comparison is **Precision vs. Recall**:

- Logistic Regression catches **92% of fraud** (excellent recall) but only 6% of its alerts are
  real — about 1,386 false alarms. Unusable in practice.
- The **MLP** finds a far better balance: F1 of 0.825 versus ~0.12 for the simpler models.

This is a good talking point for the presentation: `class_weight="balanced"` pushes the simple
models to flag aggressively, trading precision for recall. The neural network learns a genuinely
better boundary instead of just shifting the threshold.

The live demo uses the MLP by default (`ACTIVE_MODEL_NAME` in `.env`) — change it to compare
models live without retraining.

---

## 6. The simulation

22 fictional bots across 22 world cities trade continuously.

### Bot profiles

| Profile | Starting balance | Typical transaction |
|---|---|---|
| `high_roller` | $500k – $2M | $20,000 – $150,000 |
| `regular` | $5k – $50k | $100 – $8,000 |
| `dormant` | $100 – $2,000 | $50 – $800 |

Profiles matter for the comparison: the rule engine measures each bot against **its own**
baseline, so a high roller's routine transfer is not mistaken for an anomaly.

### Realistic traffic

Real businesses pay the same handful of counterparties repeatedly. Each bot therefore has **5
regular partners** and only goes somewhere new ~12% of the time. This gives every bot a stable
"normal" pattern — without it, the unusual-location rule would fire constantly and alerts would
be worthless.

### Injected anomalies

Roughly **5%** of transactions carry a deliberate fraud-like pattern and **3%** deliberately
exceed the sender's balance. Anomalies take one of two shapes:

- An **oversized payment** (8–20× the bot's average) → trips the high-amount rule.
- A **rapid burst** (10–14 payments from one account) → trips the velocity rule.

This produces a realistic mix: roughly **85% completed, ~11% suspicious, ~3% failed**. Most
traffic in a real payment network is perfectly legitimate, and the demo reflects that.

### Honesty guarantee

Every line drawn on the globe and every row in the feed corresponds to a **committed database
row**. The broadcast payload is built only *after* `db.commit()` succeeds, so the UI can never
display activity that was not actually recorded. The frontend invents nothing.

---

## 7. Architecture and request flow

```
┌──────────────── Browser ────────────────┐
│  globe.gl 3D globe   │   live feed      │
│  (one arc per txn)   │   alerts/failed  │
│                      │   accounts       │
└──────── WebSocket ───┴──── REST ────────┘
                │                │
┌───────────────┴────────────────┴────────┐
│            FastAPI (main.py)            │
│  ┌────────────────────────────────────┐ │
│  │   simulator.py  (async loop)       │ │
│  │      │                             │ │
│  │      ├──► rule_engine.py  ◄── if/else
│  │      ├──► ml_service.py   ◄── trained model
│  │      └──► commit ──► broadcast     │ │
│  └────────────────────────────────────┘ │
└──────────────────┬──────────────────────┘
                   │
              PostgreSQL
        (bots, transactions, detections)
```

### One transaction, end to end

1. The simulator loop picks a sender (usually a regular partner as receiver) and an amount
   appropriate to the sender's profile.
2. **`rule_engine.evaluate_transaction()`** applies the hand-written rules.
3. **`ml_service.predict()`** scores the same transaction with the trained model.
4. The final status is decided: a balance failure always wins; otherwise *either* system
   flagging it raises `SUSPICIOUS`. Both verdicts are stored separately.
5. Balances are updated and the transaction + detection rows are committed.
6. Only then is the payload broadcast over the WebSocket to every connected browser.

### Why the loop uses a worker thread

Database access and scikit-learn inference are **blocking** calls. Running them directly on the
event loop would stall the WebSocket and every API request at higher transaction rates, so
`create_transaction()` is a plain synchronous function executed via `asyncio.to_thread()`.

### Why the frontend also polls

A WebSocket can go **silently stale** — it stops delivering messages without ever firing a
`close` or `error` event, leaving the feed frozen with no visible error. The frontend therefore
polls `/api/transactions` every 2 seconds as a safety net, independent of socket health, and
de-duplicates by transaction ID. The socket provides instant updates; the poll guarantees the
feed can never get permanently stuck.

---

## 8. Project structure

```
backend/app/
  main.py               FastAPI app: REST endpoints, WebSocket, serves the frontend
  simulator.py          The transaction generator loop and Run/Pause/Reset logic
  rule_engine.py        Traditional programming — the hand-written if/else rules
  ml_service.py         Loads the trained model and scores live transactions
  websocket_manager.py  Tracks connected clients and broadcasts events
  models.py             SQLAlchemy tables: Bot, Transaction, Detection
  database.py           Engine and session setup
  seed.py               Creates tables, seeds the 22 bots and demo history
  locations.py          The 22 cities with coordinates for the globe
  config.py             Environment-driven settings

ml/
  preprocess.py         Load, scale, stratified split, save scalers + stats
  train_models.py       Train and evaluate all three models, save artifacts
  data/raw/             The dataset (gitignored)
  data/processed/       Train/test splits (gitignored)
  models/               Saved .joblib models + metrics.json (gitignored)

frontend/
  index.html            Dashboard markup
  css/style.css         Design tokens and all styling
  js/app.js             Globe, live feed, modals, accounts explorer
```

### The frontend

Plain HTML/CSS/JS with no build step — open the URL and it runs.

- **Globe** (globe.gl / three.js) — a daytime earth with all 22 cities labelled. Each
  transaction draws exactly **one** streak that flies from origin to destination, pulses on
  arrival, and is then removed. Historical rows loaded on page load deliberately draw *no*
  line, because a line means "this is happening right now".
- **Side panel** — a scannable list only: live feed, alerts, failed, accounts, model metrics.
- **Detail modal** — clicking a transaction or an account opens a wide modal. Transaction and
  account views link to each other (sender → account → transaction …) with a Back button,
  Esc-to-close, and backdrop click. Details live here rather than inline because the 430px
  panel is too narrow to show them without becoming unreadable.

---

## 9. API reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/bots` | All bots with balances and profiles |
| `GET` | `/api/bots/{id}` | One bot: profile, stats, and its transaction history |
| `GET` | `/api/transactions?limit=N` | Recent transactions, newest first |
| `GET` | `/api/transactions/{id}` | A single transaction with both verdicts |
| `GET` | `/api/locations` | City coordinates for the globe |
| `GET` | `/api/model-metrics` | Real evaluation metrics from `metrics.json` |
| `GET` | `/api/simulator/status` | Whether the simulator is running, and its rate |
| `POST` | `/api/simulator/run?tps=N` | Start generating |
| `POST` | `/api/simulator/pause` | Stop generating |
| `POST` | `/api/simulator/reset` | Clear history, reseed, preserve running state |
| `WS` | `/ws` | Live transaction stream |

`/api/locations` exists so the frontend never keeps its own copy of the coordinates — a drifting
duplicate would silently draw routes in the wrong place.

---

## 10. Database schema

**`bots`** — `id`, `account_id`, `display_name`, `city`, `country`, `balance`, `profile`, `created_at`

**`transactions`** — `id`, `sender_id` → bots, `receiver_id` → bots, `amount`, `currency`,
`origin_city/country`, `destination_city/country`, `status`, `timestamp`

**`detections`** — `id`, `transaction_id` → transactions, `rule_flagged`, `rule_reason`,
`model_name`, `model_flagged`, `model_probability`, `final_status`

The split between `transactions` and `detections` is deliberate: a transaction is *what
happened*, a detection is *what the two systems concluded about it*. Keeping both verdicts in
one row with separate columns is what makes the side-by-side comparison possible.

---

## 11. Configuration

Set in `.env` (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/fraud_detection` | PostgreSQL connection |
| `DEFAULT_TPS` | `3` | Transactions per second |
| `ACTIVE_MODEL_NAME` | `mlp_ann` | Which model scores live traffic (`logistic_regression`, `decision_tree`, `mlp_ann`) |

`.env` is gitignored — never commit real credentials.

---

## 12. Design decisions worth knowing

These are the non-obvious choices, and why they were made:

- **Reset keeps the simulation running.** Pausing on reset made the dashboard look broken —
  users assumed the live feed had died when it was simply stopped.
- **Reset waits for in-flight work.** `pause()` awaits the cancelled task, otherwise a
  transaction being written in a worker thread lands in the database *after* the table was
  cleared.
- **Near-empty accounts are skipped as senders.** A drained bot would otherwise be picked
  repeatedly and fail the balance check forever. The balance cap also takes priority over the
  minimum amount, for the same reason.
- **Partner countries count as already known.** Otherwise the location rule flags a bot's
  long-standing trading partner as a brand new destination the first time it appears.
- **Each bot's baseline is weighted as prior observations.** Real history blends into the
  profile average gradually instead of replacing it on the very first row.
- **Frontend files are served with `Cache-Control: no-cache`.** A stale cached `app.js` throws
  on load, which silently breaks every button and the WebSocket with no visible error.
- **Globe arcs are transient.** Accumulating arcs made the globe look busy with activity that
  had already finished.

---

## 13. Scope and limitations

**Out of scope by design:** real banking or payment integrations, real money, production
hardening, automatic retraining, and deep learning.

**Known limitations:**
- All identities, accounts and transactions are fictional and synthetically generated.
- The ML model never sees geography — that information belongs to the rule engine
  ([see above](#a-limitation-we-did-not-hide)).
- `SUSPICIOUS` means *flagged for review*, never a confirmed crime. The UI deliberately uses
  "suspicious" and "model flagged" language throughout.
- There is no automated test suite; this is an MVP intended for manual testing.
