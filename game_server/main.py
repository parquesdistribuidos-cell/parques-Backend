"""
Game Server WebSocket completo — Parqués Distribuido.

Maneja: auth, lobby, colores, partida completa, chat, bot, Berkeley.
"""
import asyncio
import logging
from typing import Dict, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from .protocolo import construir, parsear, error
from .sala import Sala, JugadorEnSala, generar_pin, ESTADO_ESPERANDO, ESTADO_EN_PARTIDA, ESTADO_TERMINADA
from .partida import Partida
from shared.auth_jwt import decodificar_token
from shared.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("game_server")

salas: Dict[str, Sala] = {}
partidas: Dict[str, Partida] = {}
salas_lock = asyncio.Lock()
partida_id_counter = 0


async def enviar(ws, msg: str):
    try:
        await ws.send(msg)
    except Exception:
        pass


async def broadcast_sala(sala: Sala, msg: str, excluir_ws=None):
    tareas = [enviar(j.websocket, msg) for j in sala.jugadores if j.websocket is not excluir_ws]
    if tareas:
        await asyncio.gather(*tareas, return_exceptions=True)


def sala_de(usuario_id: int) -> Optional[Sala]:
    for s in salas.values():
        if s.buscar_jugador(usuario_id):
            return s
    return None


# ============================================
# Handlers
# ============================================

async def h_listar_salas(ws, payload, user):
    async with salas_lock:
        lista = [
            {"pin": s.pin, "nombre": s.nombre, "jugadores": len(s.jugadores), "estado": s.estado}
            for s in salas.values() if s.estado == ESTADO_ESPERANDO
        ]
    await enviar(ws, construir("LISTA_SALAS", {"salas": lista}))


async def h_crear_sala(ws, payload, user):
    nombre = payload.get("nombre", f"Sala de {user['username']}")
    async with salas_lock:
        if sala_de(user["usuario_id"]):
            await enviar(ws, error("YA_EN_SALA", "Ya estás en una sala"))
            return
        pin = generar_pin(set(salas.keys()))
        sala = Sala(pin=pin, nombre=nombre, creador_id=user["usuario_id"])
        js = JugadorEnSala(user["usuario_id"], user["username"], ws)
        sala.jugadores.append(js)
        salas[pin] = sala
    await enviar(ws, construir("SALA_CREADA", {"pin": pin, "nombre": nombre}))
    await broadcast_sala(sala, construir("SALA_ACTUALIZADA", sala.to_dict()))


async def h_unirse_sala(ws, payload, user):
    pin = payload.get("pin", "").upper().strip()
    async with salas_lock:
        sala = salas.get(pin)
        if not sala:
            await enviar(ws, error("SALA_NO_EXISTE", f"PIN {pin} no existe"))
            return
    async with sala.lock:
        if sala.estado != ESTADO_ESPERANDO:
            await enviar(ws, error("SALA_EN_PARTIDA", "Partida en curso"))
            return
        if sala.esta_llena():
            await enviar(ws, error("SALA_LLENA", "La sala está llena"))
            return
        if sala.buscar_jugador(user["usuario_id"]):
            await enviar(ws, error("YA_EN_SALA", "Ya estás en esta sala"))
            return
        js = JugadorEnSala(user["usuario_id"], user["username"], ws)
        sala.jugadores.append(js)
    await enviar(ws, construir("SALA_CREADA", {"pin": pin, "nombre": sala.nombre}))
    await broadcast_sala(sala, construir("SALA_ACTUALIZADA", sala.to_dict()))


async def h_agregar_bot(ws, payload, user):
    """Agrega un bot a la sala actual del usuario."""
    sala = sala_de(user["usuario_id"])
    if not sala:
        await enviar(ws, error("NO_EN_SALA", "No estás en ninguna sala"))
        return
    async with sala.lock:
        if sala.esta_llena():
            await enviar(ws, error("SALA_LLENA", "La sala está llena"))
            return
        colores = sala.colores_disponibles()
        if not colores:
            await enviar(ws, error("SIN_COLORES", "No hay colores disponibles"))
            return
        bot_id = -(len([j for j in sala.jugadores if j.es_bot]) + 1)
        bot_nombre = payload.get("nombre", f"BOT_{len(sala.jugadores)+1}")
        js_bot = JugadorEnSala(bot_id, bot_nombre, ws, es_bot=True)
        js_bot.color = colores[0]
        js_bot.listo = True
        sala.jugadores.append(js_bot)
    await broadcast_sala(sala, construir("SALA_ACTUALIZADA", sala.to_dict()))


async def h_elegir_color(ws, payload, user):
    sala = sala_de(user["usuario_id"])
    if not sala:
        await enviar(ws, error("NO_EN_SALA", "No estás en ninguna sala"))
        return
    color = payload.get("color")
    async with sala.lock:
        disponibles = sala.colores_disponibles()
        js = sala.buscar_jugador(user["usuario_id"])
        if js and js.color:
            disponibles.append(js.color)
        if color not in disponibles:
            await enviar(ws, error("COLOR_OCUPADO", f"Color {color} no disponible"))
            return
        js.color = color
        js.listo = False
    await broadcast_sala(sala, construir("SALA_ACTUALIZADA", sala.to_dict()))


async def h_marcar_listo(ws, payload, user):
    sala = sala_de(user["usuario_id"])
    if not sala:
        await enviar(ws, error("NO_EN_SALA", "No estás en ninguna sala"))
        return
    async with sala.lock:
        js = sala.buscar_jugador(user["usuario_id"])
        if not js.color:
            await enviar(ws, error("FALTA_COLOR", "Elige un color primero"))
            return
        js.listo = payload.get("listo", True)
        todos_listos = sala.todos_listos()
        if todos_listos:
            sala.estado = ESTADO_EN_PARTIDA

    await broadcast_sala(sala, construir("SALA_ACTUALIZADA", sala.to_dict()))

    if sala.estado == ESTADO_EN_PARTIDA:
        asyncio.create_task(_iniciar_partida(sala))


async def _iniciar_partida(sala: Sala):
    global partida_id_counter
    partida_id_counter += 1
    partida = Partida(jugadores_sala=list(sala.jugadores), partida_id=partida_id_counter)
    partidas[sala.pin] = partida
    try:
        await partida.iniciar()
    except Exception as e:
        logger.exception(f"Error en partida {sala.pin}: {e}")
    finally:
        sala.estado = ESTADO_TERMINADA
        async with salas_lock:
            salas.pop(sala.pin, None)
        partidas.pop(sala.pin, None)


async def h_chat(ws, payload, user):
    sala = sala_de(user["usuario_id"])
    if not sala:
        return
    contenido = str(payload.get("contenido", "")).strip()[:300]
    if not contenido:
        return
    await broadcast_sala(sala, construir("MENSAJE_CHAT", {
        "usuario_id": user["usuario_id"],
        "username": user["username"],
        "contenido": contenido,
        "timestamp": __import__("time").time() * 1000,
    }))


async def h_salir_sala(ws, payload, user):
    sala = sala_de(user["usuario_id"])
    if not sala:
        return
    async with sala.lock:
        js = sala.buscar_jugador(user["usuario_id"])
        if js:
            sala.jugadores.remove(js)
    if not sala.jugadores:
        async with salas_lock:
            salas.pop(sala.pin, None)
    else:
        await broadcast_sala(sala, construir("SALA_ACTUALIZADA", sala.to_dict()))


async def h_accion_partida(ws, payload, user, tipo):
    """Redirige acciones de partida al orquestador."""
    sala = sala_de(user["usuario_id"])
    if sala and sala.pin in partidas:
        partidas[sala.pin].recibir_mensaje(tipo, payload, user["usuario_id"])


async def h_recomendacion(ws, payload, user):
    """Sugiere la mejor jugada al jugador actual."""
    sala = sala_de(user["usuario_id"])
    if not sala or sala.pin not in partidas:
        await enviar(ws, error("SIN_PARTIDA", "No hay partida activa"))
        return
    partida = partidas[sala.pin]
    jugador = partida.jugadores.get(user["usuario_id"])
    if not jugador or partida.dados_actuales is None:
        await enviar(ws, error("SIN_DADOS", "Aún no hay dados lanzados"))
        return
    movs = partida.motor.calcular_movimientos_legales(
        partida.tablero, jugador, partida.dados_actuales
    )
    if not movs:
        await enviar(ws, construir("RECOMENDACION", {
            "ficha_id": None,
            "justificacion": "No tienes movimientos posibles con estos dados.",
        }))
        return
    from .bot_estrategia import elegir_movimiento_bot
    mejor = elegir_movimiento_bot(movs, partida.tablero, jugador)
    justificaciones = {
        "meta": "Esta jugada lleva tu ficha directamente a la meta. ¡Es el movimiento ganador!",
        "captura": f"Puedes capturar una ficha rival y mandarla a la cárcel.",
        "recta": "Entras o avanzas en tu recta final, acercándote a la victoria.",
    }
    desc = mejor.destino_descripcion.lower()
    if "meta" in desc:
        just = justificaciones["meta"]
    elif "captura" in desc:
        just = justificaciones["captura"]
    elif "recta" in desc:
        just = justificaciones["recta"]
    else:
        just = f"Mueve la ficha {mejor.ficha_id} {mejor.valor} casillas hacia {mejor.destino_descripcion}."
    await enviar(ws, construir("RECOMENDACION", {
        "ficha_id": mejor.ficha_id,
        "valor": mejor.valor,
        "dado": mejor.dado,
        "destino": mejor.destino_descripcion,
        "justificacion": just,
    }))


async def h_berkeley_respuesta(ws, payload, user):
    sala = sala_de(user["usuario_id"])
    if sala and sala.pin in partidas:
        ts = payload.get("timestamp_cliente", __import__("time").time() * 1000)
        partidas[sala.pin].registrar_berkeley(user["usuario_id"], ts)


# ============================================
# Dispatch
# ============================================

HANDLERS = {
    "LISTAR_SALAS": h_listar_salas,
    "CREAR_SALA": h_crear_sala,
    "UNIRSE_SALA": h_unirse_sala,
    "AGREGAR_BOT": h_agregar_bot,
    "ELEGIR_COLOR": h_elegir_color,
    "MARCAR_LISTO": h_marcar_listo,
    "ENVIAR_CHAT": h_chat,
    "SALIR_SALA": h_salir_sala,
    "SOLICITAR_RECOMENDACION": h_recomendacion,
    "BERKELEY_RESPUESTA": h_berkeley_respuesta,
}

ACCIONES_PARTIDA = {"LANZAR_DADOS", "MOVER_FICHA", "ELEGIR_FICHA_QUEMAR", "SACAR_DE_CARCEL"}


async def manejar_cliente(websocket):
    user = None
    try:
        try:
            primer = await asyncio.wait_for(websocket.recv(), timeout=10)
        except asyncio.TimeoutError:
            await enviar(websocket, error("TIMEOUT", "Timeout de autenticación"))
            return

        try:
            msg = parsear(primer)
        except ValueError as e:
            await enviar(websocket, error("FORMATO_INVALIDO", str(e)))
            return

        if msg["type"] != "AUTH":
            await enviar(websocket, error("AUTH_REQUERIDA", "Primer mensaje debe ser AUTH"))
            return

        token = msg["payload"].get("token")
        if not token:
            await enviar(websocket, error("TOKEN_INVALIDO", "Falta el token"))
            return
        info = decodificar_token(token)
        if not info:
            await enviar(websocket, error("TOKEN_INVALIDO", "JWT inválido o expirado"))
            return

        user = {"usuario_id": int(info["sub"]), "username": info.get("username", "user")}
        await enviar(websocket, construir("AUTH_OK", user))
        logger.info(f"Conectado: {user['username']}")

        async for raw in websocket:
            try:
                msg = parsear(raw)
            except ValueError as e:
                await enviar(websocket, error("FORMATO_INVALIDO", str(e)))
                continue

            tipo = msg["type"]

            if tipo in ACCIONES_PARTIDA:
                await h_accion_partida(websocket, msg["payload"], user, tipo)
                continue

            handler = HANDLERS.get(tipo)
            if handler is None:
                await enviar(websocket, error("TIPO_DESCONOCIDO", f"No se reconoce: {tipo}"))
                continue
            try:
                await handler(websocket, msg["payload"], user)
            except Exception as e:
                logger.exception(f"Error handler {tipo}: {e}")
                await enviar(websocket, error("ERROR_INTERNO", str(e)))

    except ConnectionClosed:
        pass
    except Exception as e:
        logger.exception(f"Error conexión: {e}")
    finally:
        if user:
            uid = user["usuario_id"]
            sala = sala_de(uid)
            if sala:
                if sala.pin in partidas:
                    partidas[sala.pin].marcar_desconectado(uid)
                async with sala.lock:
                    js = sala.buscar_jugador(uid)
                    if js:
                        sala.jugadores.remove(js)
                if sala.jugadores:
                    await broadcast_sala(sala, construir("SALA_ACTUALIZADA", sala.to_dict()))
                else:
                    async with salas_lock:
                        salas.pop(sala.pin, None)
            logger.info(f"Desconectado: {user['username']}")


async def main():
    host = settings.GAME_SERVER_HOST
    port = settings.GAME_SERVER_PORT
    logger.info(f"Game Server en ws://{host}:{port}")
    async with websockets.serve(
        manejar_cliente,
        host,
        port,
        origins=None,
        ping_interval=30,
        ping_timeout=10,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Game Server detenido.")
