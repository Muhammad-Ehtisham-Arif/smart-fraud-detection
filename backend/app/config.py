import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

project_folder = Path(__file__).parent.parent.parent

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/fraud_detection",
)

DEFAULT_TPS = float(os.getenv("DEFAULT_TPS", "3"))

MODEL_DIR = os.getenv("MODEL_DIR", str(project_folder / "ml" / "models"))

ACTIVE_MODEL_NAME = os.getenv("ACTIVE_MODEL_NAME", "mlp_ann")

FRONTEND_DIR = project_folder / "frontend"
