"""
Connexion PostgreSQL — configurable via variables d'environnement.

Variables attendues (avec valeurs par défaut entre parenthèses) :
  PFA_DB_HOST     (localhost)
  PFA_DB_PORT     (5432)
  PFA_DB_NAME     (maritime_docs)
  PFA_DB_USER     (postgres)
  PFA_DB_PASSWORD (postgres)
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Charge backend/.env automatiquement — plus besoin de taper les $env:... à chaque terminal
load_dotenv(Path(__file__).resolve().parent / ".env")

DB_HOST = os.getenv("PFA_DB_HOST", "localhost")
DB_PORT = os.getenv("PFA_DB_PORT", "5432")
DB_NAME = os.getenv("PFA_DB_NAME", "maritime_docs")
DB_USER = os.getenv("PFA_DB_USER", "postgres")
DB_PASSWORD = os.getenv("PFA_DB_PASSWORD", "postgres")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def init_db() -> None:
    """
    Exécute schema.sql directement (CREATE TABLE IF NOT EXISTS partout,
    donc idempotent — sûr à relancer plusieurs fois). On exécute le fichier
    tel quel plutôt que de passer par l'ORM, pour respecter fidèlement les
    CHECK, TEXT[], et autres détails PostgreSQL du schéma fourni.
    """
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


if __name__ == "__main__":
    init_db()
    print(f"Tables créées avec succès sur {DB_HOST}:{DB_PORT}/{DB_NAME} (à partir de schema.sql)")