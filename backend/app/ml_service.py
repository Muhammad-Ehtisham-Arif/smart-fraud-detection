from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .config import ACTIVE_MODEL_NAME, MODEL_DIR

model = None
feature_names = None
time_scaler = None
amount_scaler = None
pca_statistics = None


def load_artifacts():
    global model, feature_names, time_scaler, amount_scaler, pca_statistics

    model_folder = Path(MODEL_DIR).resolve()

    model = joblib.load(model_folder / f"{ACTIVE_MODEL_NAME}.joblib")
    feature_names = joblib.load(model_folder / "feature_columns.joblib")
    time_scaler = joblib.load(model_folder / "scaler_time.joblib")
    amount_scaler = joblib.load(model_folder / "scaler_amount.joblib")
    pca_statistics = joblib.load(model_folder / "v_feature_stats.joblib")

    return model


def build_feature_row(amount, time_value, fraud_pattern):
    random = np.random.default_rng()
    values = {}

    for name in feature_names:
        if name == "Time" or name == "Amount":
            continue

        category = "fraud" if fraud_pattern else "normal"
        mean, std = pca_statistics[name][category]

        values[name] = random.normal(mean, std)

    values["Time"] = time_scaler.transform(pd.DataFrame({"Time": [time_value]}))[0][
        0
    ]

    values["Amount"] = amount_scaler.transform(pd.DataFrame({"Amount": [amount]}))[0][
        0
    ]

    row = [values[name] for name in feature_names]

    return pd.DataFrame([row], columns=feature_names)


def predict(amount, time_value, fraud_pattern=False):
    if model is None:
        load_artifacts()

    features = build_feature_row(amount, time_value, fraud_pattern)

    fraud_probability = float(model.predict_proba(features)[0][1])
    prediction = int(model.predict(features)[0])

    return {
        "model_name": ACTIVE_MODEL_NAME,
        "flagged": prediction == 1,
        "probability": round(fraud_probability, 4),
    }
