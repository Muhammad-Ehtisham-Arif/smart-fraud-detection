from pathlib import Path

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ML_FOLDER = Path(__file__).parent
RAW_FILE = ML_FOLDER / "data" / "raw" / "creditcard.csv"
PROCESSED_FOLDER = ML_FOLDER / "data" / "processed"
MODELS_FOLDER = ML_FOLDER / "models"

LABEL_COLUMN = "Class"
COLUMNS_TO_SCALE = ["Time", "Amount"]
TEST_SIZE = 0.2
RANDOM_SEED = 42
MAX_ROWS = 1_000_000


def load_dataset():
    data = pd.read_csv(RAW_FILE)

    if len(data) > MAX_ROWS:
        data = data.sample(n=MAX_ROWS, random_state=RANDOM_SEED)

    total = len(data)
    fraud = int(data[LABEL_COLUMN].sum())
    normal = total - fraud

    print(f"Loaded {total} rows")
    print(f"Normal: {normal} ({normal / total:.4%})")
    print(f"Fraud: {fraud} ({fraud / total:.4%})")

    return data


def scale_columns(train_features, test_features):
    for column in COLUMNS_TO_SCALE:
        scaler = StandardScaler()

        train_features[column] = scaler.fit_transform(train_features[[column]])

        test_features[column] = scaler.transform(test_features[[column]])

        joblib.dump(scaler, MODELS_FOLDER / f"scaler_{column.lower()}.joblib")


def calculate_feature_statistics(train_features, train_labels):
    statistics = {}

    for column in train_features.columns:
        if column.startswith("V"):
            normal = train_features.loc[train_labels == 0, column]
            fraud = train_features.loc[train_labels == 1, column]

            statistics[column] = {
                "normal": (float(normal.mean()), float(normal.std())),
                "fraud": (float(fraud.mean()), float(fraud.std())),
            }

    return statistics


def save_processed_data(train_features, test_features, train_labels, test_labels):
    PROCESSED_FOLDER.mkdir(parents=True, exist_ok=True)

    train_features.to_csv(PROCESSED_FOLDER / "X_train.csv", index=False)
    test_features.to_csv(PROCESSED_FOLDER / "X_test.csv", index=False)

    train_labels.to_csv(PROCESSED_FOLDER / "y_train.csv", index=False)
    test_labels.to_csv(PROCESSED_FOLDER / "y_test.csv", index=False)


def main():
    MODELS_FOLDER.mkdir(parents=True, exist_ok=True)

    data = load_dataset()

    features = data.drop(columns=[LABEL_COLUMN])
    labels = data[LABEL_COLUMN]

    train_features, test_features, train_labels, test_labels = train_test_split(
        features, labels, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=labels
    )

    scale_columns(train_features, test_features)

    save_processed_data(train_features, test_features, train_labels, test_labels)

    joblib.dump(list(features.columns), MODELS_FOLDER / "feature_columns.joblib")

    feature_statistics = calculate_feature_statistics(train_features, train_labels)

    joblib.dump(feature_statistics, MODELS_FOLDER / "v_feature_stats.joblib")

    print(f"Train set: {len(train_features)} rows")
    print(f"Test set: {len(test_features)} rows")
    print("Preprocessing complete. Processed files saved to ml/data/processed/")


if __name__ == "__main__":
    main()
