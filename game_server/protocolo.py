"""
Mensajes del protocolo WebSocket.

Helpers para construir y validar mensajes.
"""

import json
import time
from typing import Any


def construir(tipo: str, payload: dict | None = None) -> str:
    """Construye un mensaje JSON listo para enviar."""
    return json.dumps({
        "type": tipo,
        "payload": payload or {},
        "timestamp": int(time.time() * 1000),
    })


def parsear(raw: str) -> dict:
    """Parsea un mensaje recibido. Lanza ValueError si es inválido."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}")
    if not isinstance(msg, dict):
        raise ValueError("El mensaje debe ser un objeto JSON")
    if "type" not in msg:
        raise ValueError("Falta el campo 'type'")
    msg.setdefault("payload", {})
    return msg


def error(codigo: str, mensaje: str) -> str:
    """Construye un mensaje de error."""
    return construir("ERROR", {"codigo": codigo, "mensaje": mensaje})
