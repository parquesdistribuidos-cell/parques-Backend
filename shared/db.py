"""
Conexión a PostgreSQL con SQLAlchemy async.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    """Base para todos los modelos ORM."""
    pass


# Motor asíncrono compartido
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Cambiar a True para ver todas las queries SQL
    pool_pre_ping=True,
)

# Factory de sesiones
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """Dependencia de FastAPI: yields una sesión que se cierra al terminar."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
