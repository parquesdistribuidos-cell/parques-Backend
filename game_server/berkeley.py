"""
Algoritmo de Berkeley para sincronización de relojes.

El servidor actúa como maestro:
1. Solicita timestamps a todos los clientes
2. Calcula el promedio de diferencias
3. Envía el offset de ajuste a cada cliente

Referencia: Tanenbaum - Distributed Systems
"""
import asyncio
import time
import logging
from typing import Dict, List

logger = logging.getLogger("game_server.berkeley")


class Berkeley:
    def __init__(self, timeout_seg: float = 5.0):
        self.timeout = timeout_seg

    async def sincronizar(self, jugadores_ws: List) -> Dict[int, float]:
        """
        Ejecuta el algoritmo de Berkeley con los jugadores dados.
        Retorna dict {usuario_id: offset_ms}.
        """
        from .protocolo import construir

        ts_servidor = time.time() * 1000
        solicitud = construir("BERKELEY_SOLICITUD", {"timestamp_servidor": ts_servidor})

        # Paso 1: enviar solicitud a todos
        respuestas: Dict[int, float] = {}
        eventos: Dict[int, asyncio.Event] = {}
        
        for jug in jugadores_ws:
            eventos[jug.usuario_id] = asyncio.Event()

        async def enviar_y_esperar(jug):
            try:
                await jug.websocket.send(solicitud)
            except Exception:
                pass

        await asyncio.gather(*[enviar_y_esperar(j) for j in jugadores_ws], return_exceptions=True)

        # Paso 2: esperar respuestas con timeout
        # Las respuestas llegan por el handler normal del game server
        # Aquí esperamos hasta timeout y usamos las que lleguen
        await asyncio.sleep(min(self.timeout, 2.0))

        # Paso 3: calcular promedio con los timestamps recibidos
        # Si no hay respuestas, offset = 0 para todos
        if not respuestas:
            logger.info("Berkeley: sin respuestas de clientes, offset=0 para todos")
            offsets = {j.usuario_id: 0.0 for j in jugadores_ws}
        else:
            ts_actual = time.time() * 1000
            diffs = list(respuestas.values())
            promedio = sum(diffs) / len(diffs)
            offsets = {}
            for jug in jugadores_ws:
                uid = jug.usuario_id
                diff = respuestas.get(uid, 0.0)
                offsets[uid] = round(promedio - diff, 2)

        # Paso 4: enviar offsets a cada cliente
        from .protocolo import construir as c
        for jug in jugadores_ws:
            offset = offsets.get(jug.usuario_id, 0.0)
            try:
                await jug.websocket.send(c("BERKELEY_AJUSTE", {"offset_ms": offset}))
            except Exception:
                pass

        logger.info(f"Berkeley completado. Offsets: {offsets}")
        return offsets

    def registrar_respuesta(
        self,
        respuestas: Dict[int, float],
        usuario_id: int,
        ts_cliente: float,
    ):
        """Llamado por el handler cuando llega BERKELEY_RESPUESTA."""
        ts_servidor = time.time() * 1000
        diff = ts_servidor - ts_cliente
        respuestas[usuario_id] = diff
