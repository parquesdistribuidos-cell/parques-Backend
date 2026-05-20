# Parqués Distribuido — Backend

Python 3.11 + FastAPI + websockets + asyncio + SQLAlchemy + PostgreSQL

## Servicios

Este backend tiene DOS servicios que se despliegan por separado en Railway:

### 1. API REST (puerto 8000)
```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

### 2. Game Server WebSocket (puerto 8001)
```bash
python -m game_server.main
```

## Variables de entorno en Railway

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | Railway la genera automáticamente al agregar PostgreSQL |
| `JWT_SECRET` | Secreto para firmar JWT (mismo en API y Game Server) |
| `GAME_SERVER_HOST` | `0.0.0.0` |

## Correr en local

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt

# API
uvicorn api.main:app --reload

# Game Server
python -m game_server.main
```

## Tests

```bash
pytest tests/ -v
```

## Desplegar en Railway

1. Conecta este repo en railway.app
2. Crea dos servicios: uno para API, otro para Game Server
3. Agrega PostgreSQL como plugin
4. Configura las variables de entorno
5. El `railway.json` configura el comando de inicio de la API
6. Para el Game Server usa `railway.gameserver.json` como configuración
