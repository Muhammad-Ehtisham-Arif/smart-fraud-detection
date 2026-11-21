import json
from pathlib import Path

import joblib
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)
from sklearn.neural_network import MLPClassifier
from sklearn.tree import DecisionTreeClassifier

ML_FOLDER = Path(__file__).parent
PROCESSED_FOLDER = ML_FOLDER / "data" / "processed"
MODELS_FOLDER = ML_FOLDER / "models"

RANDOM_SEED = 42


MODELS = [
    (
        "logistic_regression",
        "Logistic Regression",
        LogisticRegression(
            max_iter=1000, class_weight="balanced", random_state=RANDOM_SEED
        ),
    ),
    (
        "decision_tree",
        "Decision Tree",
        DecisionTreeClassifier(
            max_depth=8, class_weight="balanced", random_state=RANDOM_SEED
        ),
    ),
    (
        "mlp_ann",
        "MLPClassifier (small ANN)",
        MLPClassifier(hidden_layer_sizes=(16,), max_iter=300, random_state=RANDOM_SEED),
    ),
]


def load_training_data():
    train_features = pd.read_csv(PROCESSED_FOLDER / "X_train.csv")
    test_features = pd.read_csv(PROCESSED_FOLDER / "X_test.csv")

    train_labels = pd.read_csv(PROCESSED_FOLDER / "y_train.csv").iloc[:, 0]
    test_labels = pd.read_csv(PROCESSED_FOLDER / "y_test.csv").iloc[:, 0]

    return train_features, test_features, train_labels, test_labels


def evaluate_model(display_name, model, test_features, test_labels):
    predictions = model.predict(test_features)

    metrics = {
        "accuracy": accuracy_score(test_labels, predictions),
        "precision": precision_score(test_labels, predictions, zero_division=0),
        "recall": recall_score(test_labels, predictions, zero_division=0),
        "f1_score": f1_score(test_labels, predictions, zero_division=0),
        "confusion_matrix": confusion_matrix(test_labels, predictions).tolist(),
    }

    print(f"\n=== {display_name} ===")
    print(f"Accuracy : {metrics['accuracy']:.4f}")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall   : {metrics['recall']:.4f}")
    print(f"F1-score : {metrics['f1_score']:.4f}")

    print("Confusion Matrix:")
    print(metrics["confusion_matrix"])

    print(
        classification_report(
            test_labels, predictions, target_names=["Normal", "Fraud"], zero_division=0
        )
    )

    return metrics


def main():
    MODELS_FOLDER.mkdir(parents=True, exist_ok=True)

    train_features, test_features, train_labels, test_labels = load_training_data()

    results = {}

    for model_file_name, display_name, model in MODELS:
        model.fit(train_features, train_labels)

        results[model_file_name] = evaluate_model(
            display_name, model, test_features, test_labels
        )

        joblib.dump(model, MODELS_FOLDER / f"{model_file_name}.joblib")

    with open(MODELS_FOLDER / "metrics.json", "w") as file:
        json.dump(results, file, indent=2)

    print(f"\nSaved trained models and metrics.json to {MODELS_FOLDER}")


if __name__ == "__main__":
    main()
