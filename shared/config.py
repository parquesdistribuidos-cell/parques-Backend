"""Configuración compartida. Lee variables de entorno."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

class Settings:
    # PostgreSQL — Railway provee DATABASE_URL directamente
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "parques")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "parques_dev_2026")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "parques_db")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))

    # Railway provee DATABASE_URL como postgresql://... necesitamos asyncpg
    _db_url = os.getenv("DATABASE_URL", "")
    if _db_url.startswith("postgresql://"):
        DATABASE_URL = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif _db_url.startswith("postgres://"):
        DATABASE_URL = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        DATABASE_URL = os.getenv(
            "DATABASE_URL",
            f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:{POSTGRES_PORT}/{POSTGRES_DB}"
        )

    # API
    API_PORT: int = int(os.getenv("PORT", os.getenv("API_PORT", "8000")))

    # Game Server
    GAME_SERVER_PORT: int = int(os.getenv("PORT", os.getenv("GAME_SERVER_PORT", "8001")))
    GAME_SERVER_HOST: str = os.getenv("GAME_SERVER_HOST", "0.0.0.0")

    # JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "cambiar_en_produccion")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

    # Frontend
    NEXT_PUBLIC_API_URL: str = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8000")
    NEXT_PUBLIC_WS_URL: str = os.getenv("NEXT_PUBLIC_WS_URL", "ws://localhost:8001")

    # Juego
    JUEGO_MAX_JUGADORES: int = 4
    JUEGO_MIN_JUGADORES: int = 2
    JUEGO_TIMEOUT_TURNO_SEG: int = int(os.getenv("JUEGO_TIMEOUT_TURNO_SEG", "60"))

settings = Settings()
