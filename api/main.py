"""FastAPI completo con todos los routers."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import auth, usuarios, estadisticas
from shared.db import Base, engine
from api.models import Usuario, Partida, Participacion, Jugada, MensajeChat  # noqa

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(
    title="Parqués Distribuido API",
    version="1.0.0",
    description="API del juego de Parqués Distribuido",
    lifespan=lifespan,
)

# CORS — acepta el dominio de Vercel y localhost
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if FRONTEND_URL:
    origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(estadisticas.router)

@app.get("/")
async def root():
    return {"message": "Parqués Distribuido API v1.0", "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "ok"}
