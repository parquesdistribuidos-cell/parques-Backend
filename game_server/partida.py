"""
Orquestador de una partida completa de parqués.

Conecta el motor de reglas con el Game Server WebSocket.
Maneja: tirada inicial, turnos, dados, movimientos, chat, victoria.
"""
import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .motor.constantes import (
    COLORES,
    SALIDA_POR_COLOR,
    ESTADO_CARCEL,
    ESTADO_TABLERO,
    ESTADO_META,
    FICHAS_POR_JUGADOR,
)
from .motor.dados import Dados, ResultadoDados
from .motor.gestor_turnos import GestorTurnos
from .motor.jugador import Jugador
from .motor.reglas import MotorReglas
from .motor.tablero import Tablero
from .protocolo import construir, error
from .sala import JugadorEnSala
from api.models import Partida as PartidaDB, Participacion as ParticipacionDB
from shared.db import AsyncSessionLocal

logger = logging.getLogger("game_server.partida")


async def _enviar(ws, msg: str):
    try:
        await ws.send(msg)
    except Exception:
        pass


async def _broadcast(jugadores: List[JugadorEnSala], msg: str, excluir_id: int = None):
    seen = set()
    tareas = []
    for j in jugadores:
        if j.usuario_id == excluir_id:
            continue
        ws_id = id(j.websocket)
        if ws_id in seen:
            continue
        seen.add(ws_id)
        tareas.append(_enviar(j.websocket, msg))
    if tareas:
        await asyncio.gather(*tareas, return_exceptions=True)


class Partida:
    """
    Ciclo de vida de una partida completa.
    Se instancia desde la Sala cuando todos los jugadores están listos.
    """

    def __init__(self, jugadores_sala: List[JugadorEnSala], partida_id: int = 0):
        self.partida_id = partida_id
        self.jugadores_sala = jugadores_sala

        # Motor
        self.tablero = Tablero()
        self.dados = Dados()
        self.motor = MotorReglas()
        self.gestor = GestorTurnos()

        # Crear jugadores del motor
        self.jugadores: Dict[int, Jugador] = {}
        for js in jugadores_sala:
            jug = Jugador(id=js.usuario_id, username=js.username, color=js.color, es_bot=js.es_bot)
            js.jugador_motor = jug
            self.jugadores[js.usuario_id] = jug
            # Inicializar fichas en cárcel
            for f in jug.fichas:
                self.tablero.encarcelar(f)

        # Estado
        self.turno_lock = asyncio.Lock()
        self.dados_actuales: Optional[ResultadoDados] = None
        self.turno_numero: int = 0
        self.activa: bool = False
        # self.bot_delay_min = 3.0
        # self.bot_delay_max = 6.0
        self.bot_delay_min = 0.5
        self.bot_delay_max = 1.0
        self.turnos_jugados: Dict[int, int] = {js.usuario_id: 0 for js in jugadores_sala}
        self.partida_db_id: Optional[int] = None
        self._inicio_ts = time.time()

        # Para esperar decisión del jugador
        self._esperando_movimiento: Optional[asyncio.Event] = None
        self._movimiento_recibido: Optional[dict] = None

        # Para Berkeley
        self._berkeley_respuestas: Dict[int, float] = {}

    # ============================================
    # Arranque
    # ============================================

    async def iniciar(self):
        """Ejecuta la secuencia completa de inicio de partida."""
        self.activa = True
        logger.info(f"Partida {self.partida_id} iniciando con {len(self.jugadores)} jugadores")

        await self._guardar_partida_inicio()

        # 1. Berkeley
        await self._ejecutar_berkeley()

        # 2. Tirada inicial para determinar primer turno
        await self._tirada_inicial()

        # 3. Loop principal del juego
        await self._loop_principal()

    async def _ejecutar_berkeley(self):
        from .berkeley import Berkeley
        bk = Berkeley()
        offsets = await bk.sincronizar(self.jugadores_sala)
        logger.info(f"Berkeley offsets: {offsets}")

    async def _guardar_partida_inicio(self):
        """Registra la partida en BD para estadísticas y ranking."""
        try:
            async with AsyncSessionLocal() as session:
                partida = PartidaDB(estado="en_curso", fecha_inicio=datetime.now(timezone.utc))
                session.add(partida)
                await session.flush()

                for js in self.jugadores_sala:
                    if js.usuario_id <= 0:
                        continue
                    session.add(
                        ParticipacionDB(
                            partida_id=partida.id,
                            usuario_id=js.usuario_id,
                            color=js.color or "",
                        )
                    )

                await session.commit()
                self.partida_db_id = partida.id
        except Exception as exc:
            logger.warning(f"No se pudo guardar la partida en BD: {exc}")

    async def _tirada_inicial(self):
        """Cada jugador tira un dado para determinar quién empieza."""
        await _broadcast(
            self.jugadores_sala,
            construir("TURNO_ASIGNADO", {
                "fase": "tirada_inicial",
                "mensaje": "Todos lanzan para ver quién empieza. Espera...",
                "jugador_id": None,
            })
        )
        await asyncio.sleep(2.0)

        tiradas = {}
        for js in self.jugadores_sala:
            r = self.dados.lanzar()
            valor = r.valor_a + r.valor_b
            tiradas[js.usuario_id] = valor
            self.gestor.registrar_tirada_inicial(js.usuario_id, valor)
            await _broadcast(
                self.jugadores_sala,
                construir("DADOS_RESULTADO", {
                    "fase": "tirada_inicial",
                    "jugador_id": js.usuario_id,
                    "username": js.username,
                    "dado_a": r.valor_a,
                    "dado_b": r.valor_b,
                    "suma": valor,
                })
            )
            await asyncio.sleep(0.3)

        self.gestor.determinar_primer_turno(list(self.jugadores.values()))

        primer = self.gestor.jugador_actual_id()
        jugador_primer = self.jugadores[primer]
        await _broadcast(
            self.jugadores_sala,
            construir("PARTIDA_INICIADA", {
                "orden_turnos": self.gestor.orden_jugadores,
                "primer_turno": primer,
                "tiradas": tiradas,
                "tablero": self.tablero.to_dict(),
                "jugadores": {str(uid): j.to_dict() for uid, j in self.jugadores.items()},
            })
        )
        logger.info(f"Primer turno: {jugador_primer.username}")

    # ============================================
    # Loop principal
    # ============================================

    async def _loop_principal(self):
        MAX_TURNOS = 2000  # Evitar bucle infinito
        turno_count = 0

        while self.activa and turno_count < MAX_TURNOS:
            turno_count += 1
            jid = self.gestor.jugador_actual_id()
            if jid is None:
                break

            jugador = self.jugadores.get(jid)
            if jugador is None:
                self.gestor.avanzar_turno()
                continue

            js = self._buscar_js(jid)
            if js is None or js.desconectado:
                self.gestor.avanzar_turno()
                ganador_abandono = self._ganador_por_abandono()
                if ganador_abandono:
                    await self._finalizar_por_abandono(ganador_abandono)
                    return
                continue

            await self._ejecutar_turno(jugador, js)

            # Verificar victoria
            ganador = self.motor.hay_ganador(list(self.jugadores.values()))
            if ganador:
                await self._finalizar(ganador)
                return

        logger.warning(f"Partida {self.partida_id} terminó por límite de turnos")
        await self._guardar_partida_fin(ganador=None, estado="abandonada")
        self.activa = False

    async def _ejecutar_turno(self, jugador: Jugador, js: JugadorEnSala):
        """Ejecuta el turno completo de un jugador."""
        self.turno_numero += 1
        retiene_turno = True
        turnos_previos = self.turnos_jugados.get(jugador.id, 0)
        es_primera_tirada_turno = True

        while retiene_turno and self.activa:
            retiene_turno = False

            # Notificar turno
            await _broadcast(
                self.jugadores_sala,
                construir("TURNO_ASIGNADO", {
                    "jugador_id": jugador.id,
                    "username": jugador.username,
                    "color": jugador.color,
                    "turno_numero": self.turno_numero,
                    "timeout_seg": 60,
                    "tablero": self.tablero.to_dict(),
                })
            )

            # Lanzar dados
            usa_tres_tiros = es_primera_tirada_turno and self._puede_tres_tiros(jugador, turnos_previos)
            if usa_tres_tiros:
                dados, hay_par = await self._lanzar_dados_hasta_par(jugador, js)
                if dados is None:
                    break
                if not hay_par:
                    jugador.pares_consecutivos = 0
                    await _broadcast(
                        self.jugadores_sala,
                        construir("SIN_MOVIMIENTOS", {
                            "jugador_id": jugador.id,
                            "username": jugador.username,
                            "dado_a": dados.valor_a,
                            "dado_b": dados.valor_b,
                        })
                    )
                    await asyncio.sleep(0.4)
                    break
            else:
                dados = await self._lanzar_dados_turno(jugador, js)
                if dados is None:
                    break
            es_primera_tirada_turno = False

            # Procesar pares
            resultado_pares = self.motor.procesar_pares(jugador, dados)

            if resultado_pares["saca_ficha"]:
                # 3 pares consecutivos: el jugador elige una ficha para quemar
                await self._manejar_tres_pares(jugador, js, dados)
                break

            # ¿Tiene fichas en cárcel y sacó par?
            if dados.es_par and jugador.fichas_en_carcel():
                await self._manejar_salida_carcel(jugador, js, dados)

            # Movimientos normales
            movs = self.motor.calcular_movimientos_legales(self.tablero, jugador, dados)

            if not movs:
                await _broadcast(
                    self.jugadores_sala,
                    construir("SIN_MOVIMIENTOS", {
                        "jugador_id": jugador.id,
                        "username": jugador.username,
                        "dado_a": dados.valor_a,
                        "dado_b": dados.valor_b,
                    })
                )
                # Consumir oportunidad si solo tiene fichas en cárcel
                if not jugador.fichas_jugables():
                    self.motor.consumir_oportunidad_salida(jugador)
            else:
                await self._pedir_y_aplicar_movimiento(jugador, js, dados, movs)

            # Broadcast estado
            await self._broadcast_estado()

            # ¿Retiene turno por par?
            if resultado_pares["retiene_turno"]:
                retiene_turno = True
                await asyncio.sleep(0.5)

        self.turnos_jugados[jugador.id] = turnos_previos + 1
        self.gestor.avanzar_turno()

    async def _lanzar_dados_turno(self, jugador: Jugador, js: JugadorEnSala) -> Optional[ResultadoDados]:
        """Espera a que el jugador lance los dados (o el bot lo hace automático)."""
        if js.es_bot:
            # await asyncio.sleep(1.2)  # Pausa visual del bot
            dados = self.dados.lanzar()
        else:
            # Esperar mensaje LANZAR_DADOS del cliente
            self._esperando_movimiento = asyncio.Event()
            self._movimiento_recibido = None

            await _enviar(
                js.websocket,
                construir("ACCION_REQUERIDA", {
                    "accion": "LANZAR_DADOS",
                    "jugador_id": jugador.id,
                })
            )

            try:
                await asyncio.wait_for(self._esperando_movimiento.wait(), timeout=60)
                msg = self._movimiento_recibido
                if msg and msg.get("type") == "LANZAR_DADOS":
                    dados = self.dados.lanzar()
                else:
                    dados = self.dados.lanzar()
            except asyncio.TimeoutError:
                logger.warning(f"Timeout esperando dados de {jugador.username}")
                dados = self.dados.lanzar()
            finally:
                self._esperando_movimiento = None

        self.dados_actuales = dados

        await _broadcast(
            self.jugadores_sala,
            construir("DADOS_RESULTADO", {
                "jugador_id": jugador.id,
                "username": jugador.username,
                "dado_a": dados.valor_a,
                "dado_b": dados.valor_b,
                "es_par": dados.es_par,
                "pares_consecutivos": jugador.pares_consecutivos,
            })
        )
        await asyncio.sleep(0.3)
        return dados

    async def _lanzar_dados_hasta_par(
        self, jugador: Jugador, js: JugadorEnSala
    ) -> tuple[Optional[ResultadoDados], bool]:
        """Permite hasta 3 tiros en el mismo turno hasta sacar par."""
        ultimo = None
        for intento in range(3):
            ultimo = await self._lanzar_dados_turno(jugador, js)
            if ultimo is None:
                return None, False
            if ultimo.es_par:
                return ultimo, True
            if intento < 2:
                await asyncio.sleep(0.4)
        return ultimo, False

    def _todas_en_carcel(self, jugador: Jugador) -> bool:
        return len(jugador.fichas_en_carcel()) == FICHAS_POR_JUGADOR

    def _puede_tres_tiros(self, jugador: Jugador, turnos_previos: int) -> bool:
        if turnos_previos == 0:
            return True
        return self._todas_en_carcel(jugador)

    async def _esperar_bot_movimiento(self):
        await asyncio.sleep(random.uniform(self.bot_delay_min, self.bot_delay_max))

    async def _manejar_salida_carcel(self, jugador: Jugador, js: JugadorEnSala, dados: ResultadoDados):
        """Permite al jugador sacar fichas de la cárcel con pares."""
        fichas_en_carcel = jugador.fichas_en_carcel()
        cantidad = 2 if dados.es_par_de_seises and len(fichas_en_carcel) >= 2 else 1

        for _ in range(cantidad):
            if not jugador.fichas_en_carcel():
                break
            resultado = self.motor.sacar_de_carcel(self.tablero, jugador, dados)
            if resultado.exito:
                await _broadcast(
                    self.jugadores_sala,
                    construir("FICHA_SALIO_CARCEL", {
                        "jugador_id": jugador.id,
                        "username": jugador.username,
                        "ficha_id": resultado.ficha_movida,
                        "color": jugador.color,
                    })
                )

    async def _pedir_y_aplicar_movimiento(
        self, jugador: Jugador, js: JugadorEnSala,
        dados: ResultadoDados, movimientos
    ):
        """Pide al jugador qué ficha mover y aplica el movimiento."""
        movs_dict = [m.to_dict() for m in movimientos]

        if js.es_bot:
            # Bot elige según heurística
            await self._esperar_bot_movimiento()
            from .bot_estrategia import elegir_movimiento_bot
            mov_elegido = elegir_movimiento_bot(movimientos, self.tablero, jugador)
        else:
            # Pedir decisión al jugador humano
            await _enviar(
                js.websocket,
                construir("ACCION_REQUERIDA", {
                    "accion": "MOVER_FICHA",
                    "jugador_id": jugador.id,
                    "movimientos_legales": movs_dict,
                    "dado_a": dados.valor_a,
                    "dado_b": dados.valor_b,
                })
            )

            self._esperando_movimiento = asyncio.Event()
            self._movimiento_recibido = None

            try:
                await asyncio.wait_for(self._esperando_movimiento.wait(), timeout=60)
                msg = self._movimiento_recibido
                if msg and msg.get("type") == "MOVER_FICHA":
                    ficha_id = msg["payload"].get("ficha_id")
                    valor = msg["payload"].get("valor")
                    mov_elegido = next(
                        (m for m in movimientos if m.ficha_id == ficha_id and m.valor == valor),
                        movimientos[0]
                    )
                else:
                    mov_elegido = movimientos[0]
            except asyncio.TimeoutError:
                logger.warning(f"Timeout esperando movimiento de {jugador.username}")
                mov_elegido = movimientos[0]
            finally:
                self._esperando_movimiento = None

        # Aplicar
        resultado = self.motor.aplicar_movimiento(
            self.tablero, jugador, mov_elegido.ficha_id, mov_elegido.valor
        )

        if resultado.exito:
            msg_payload = {
                "jugador_id": jugador.id,
                "username": jugador.username,
                "ficha_id": resultado.ficha_movida,
                "fichas_capturadas": resultado.fichas_capturadas,
                "llego_a_meta": resultado.llego_a_meta,
                "tablero": self.tablero.to_dict(),
            }
            await _broadcast(self.jugadores_sala, construir("FICHA_MOVIDA", msg_payload))

            # Notificar capturas
            for fid in resultado.fichas_capturadas:
                await _broadcast(
                    self.jugadores_sala,
                    construir("FICHA_CAPTURADA", {
                        "ficha_capturada_id": fid,
                        "captor_id": jugador.id,
                        "captor_username": jugador.username,
                    })
                )

    async def _manejar_tres_pares(self, jugador: Jugador, js: JugadorEnSala, dados: ResultadoDados):
        """El jugador elige una ficha para sacar del juego (3 pares consecutivos)."""
        fichas_en_juego = jugador.fichas_jugables()
        if not fichas_en_juego:
            return

        await _broadcast(
            self.jugadores_sala,
            construir("TRES_PARES", {
                "jugador_id": jugador.id,
                "username": jugador.username,
                "mensaje": f"{jugador.username} sacó 3 pares. Debe elegir una ficha para quemar.",
            })
        )

        if js.es_bot or not fichas_en_juego:
            ficha_elegida = fichas_en_juego[0].id
        else:
            await _enviar(js.websocket, construir("ACCION_REQUERIDA", {
                "accion": "ELEGIR_FICHA_QUEMAR",
                "fichas_disponibles": [f.to_dict() for f in fichas_en_juego],
            }))
            self._esperando_movimiento = asyncio.Event()
            self._movimiento_recibido = None
            try:
                await asyncio.wait_for(self._esperando_movimiento.wait(), timeout=30)
                msg = self._movimiento_recibido
                ficha_elegida = msg["payload"].get("ficha_id", fichas_en_juego[0].id) if msg else fichas_en_juego[0].id
            except asyncio.TimeoutError:
                ficha_elegida = fichas_en_juego[0].id
            finally:
                self._esperando_movimiento = None

        resultado = self.motor.quemar_ficha(self.tablero, jugador, ficha_elegida)
        if resultado.exito:
            await _broadcast(self.jugadores_sala, construir("FICHA_QUEMADA", {
                "jugador_id": jugador.id,
                "ficha_id": ficha_elegida,
                "tablero": self.tablero.to_dict(),
            }))

    async def _broadcast_estado(self):
        await _broadcast(
            self.jugadores_sala,
            construir("ESTADO_TABLERO", {
                "tablero": self.tablero.to_dict(),
                "jugadores": {str(uid): j.to_dict() for uid, j in self.jugadores.items()},
                "turno_actual": self.gestor.jugador_actual_id(),
            })
        )

    async def _finalizar(self, ganador: Jugador):
        self.activa = False
        logger.info(f"Partida {self.partida_id} ganada por {ganador.username}")
        await self._guardar_partida_fin(ganador=ganador, estado="terminada")
        await _broadcast(
            self.jugadores_sala,
            construir("PARTIDA_TERMINADA", {
                "ganador_id": ganador.id,
                "ganador_username": ganador.username,
                "ganador_color": ganador.color,
                "tablero": self.tablero.to_dict(),
                "estadisticas": {
                    str(uid): {
                        "fichas_en_meta": len(j.fichas_en_meta()),
                        "pares_totales": j.pares_consecutivos,
                    }
                    for uid, j in self.jugadores.items()
                }
            })
        )

    async def _guardar_partida_fin(self, ganador: Optional[Jugador], estado: str):
        if not self.partida_db_id:
            return
        try:
            async with AsyncSessionLocal() as session:
                partida = await session.get(PartidaDB, self.partida_db_id)
                if not partida:
                    return
                partida.fecha_fin = datetime.now(timezone.utc)
                partida.estado = estado
                if ganador and ganador.id > 0:
                    partida.ganador_id = ganador.id
                partida.duracion_seg = int(time.time() - self._inicio_ts)
                await session.commit()
        except Exception as exc:
            logger.warning(f"No se pudo actualizar la partida en BD: {exc}")

    # ============================================
    # Recepción de mensajes del cliente
    # ============================================

    def recibir_mensaje(self, tipo: str, payload: dict, usuario_id: int):
        """Llamado por el Game Server cuando llega un mensaje del cliente durante la partida."""
        self._movimiento_recibido = {"type": tipo, "payload": payload, "usuario_id": usuario_id}
        if self._esperando_movimiento:
            self._esperando_movimiento.set()

    def registrar_berkeley(self, usuario_id: int, ts_cliente: float):
        from .berkeley import Berkeley
        bk = Berkeley()
        bk.registrar_respuesta(self._berkeley_respuestas, usuario_id, ts_cliente)

    def _buscar_js(self, usuario_id: int) -> Optional[JugadorEnSala]:
        for js in self.jugadores_sala:
            if js.usuario_id == usuario_id:
                return js
        return None

    def marcar_desconectado(self, usuario_id: int):
        jugador = self.jugadores.get(usuario_id)
        if jugador:
            jugador.desconectado = True


    def _ganador_por_abandono(self) -> Optional[Jugador]:
        """Retorna el único jugador activo si todos los demás se desconectaron."""
        activos = [
            j for j in self.jugadores.values()
            if not j.desconectado
        ]
        if len(activos) == 1:
            return activos[0]
        return None

    async def _finalizar_por_abandono(self, ganador: Jugador):
        self.activa = False
        logger.info(
            f"Partida {self.partida_id} ganada por abandono: {ganador.username}"
        )
        await self._guardar_partida_fin(ganador=ganador, estado="terminada")
        await _broadcast(
            self.jugadores_sala,
            construir("PARTIDA_TERMINADA", {
                "ganador_id": ganador.id,
                "ganador_username": ganador.username,
                "ganador_color": ganador.color,
                "tablero": self.tablero.to_dict(),
                "motivo": "abandono",
                "estadisticas": {
                    str(uid): {
                        "fichas_en_meta": len(j.fichas_en_meta()),
                        "pares_totales": j.pares_consecutivos,
                    }
                    for uid, j in self.jugadores.items()
                }
            })
        )
