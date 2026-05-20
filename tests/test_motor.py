"""
Tests del motor de reglas del parqués.

Cubre los casos críticos del enunciado:
- Salida de cárcel con pares
- 3 pares consecutivos -> sacar ficha
- 3 oportunidades iniciales para salir de cárcel
- Captura de fichas
- Protección en seguros y recta de color
- Detección de victoria

Para ejecutar:
    pytest backend/tests/ -v

Este archivo fue desarrollado con asistencia de Claude (Anthropic).
"""

import pytest

from game_server.motor.constantes import (
    SALIDA_POR_COLOR,
    ENTRADA_RECTA_FINAL,
    RECTA_FINAL_LONGITUD,
    ESTADO_CARCEL,
    ESTADO_TABLERO,
    ESTADO_RECTA_FINAL,
    ESTADO_META,
    OPORTUNIDADES_SALIDA_INICIAL,
)
from game_server.motor.dados import Dados, ResultadoDados
from game_server.motor.ficha import Ficha
from game_server.motor.jugador import Jugador
from game_server.motor.tablero import Tablero
from game_server.motor.reglas import MotorReglas


# ============================================
# Fixtures
# ============================================

@pytest.fixture
def motor():
    return MotorReglas()


@pytest.fixture
def tablero():
    return Tablero()


@pytest.fixture
def jugador_rojo(tablero):
    jug = Jugador(id=1, username="alice", color="rojo")
    # Inicializar fichas en cárcel
    for f in jug.fichas:
        tablero.encarcelar(f)
    return jug


@pytest.fixture
def jugador_azul(tablero):
    jug = Jugador(id=2, username="bob", color="azul")
    for f in jug.fichas:
        tablero.encarcelar(f)
    return jug


# ============================================
# Tests: creación de fichas
# ============================================

def test_jugador_tiene_4_fichas(jugador_rojo):
    assert len(jugador_rojo.fichas) == 4


def test_fichas_inician_en_carcel(jugador_rojo):
    for f in jugador_rojo.fichas:
        assert f.estado == ESTADO_CARCEL


def test_ids_de_fichas_codifican_jugador(jugador_rojo):
    """Las fichas del jugador 1 deben tener ID 11, 12, 13, 14."""
    ids = sorted(f.id for f in jugador_rojo.fichas)
    assert ids == [11, 12, 13, 14]
    for f in jugador_rojo.fichas:
        assert f.jugador_id == 1


# ============================================
# Tests: dados
# ============================================

def test_dados_devuelven_valores_validos():
    dados = Dados(seed=42)
    for _ in range(50):
        r = dados.lanzar()
        assert 1 <= r.valor_a <= 6
        assert 1 <= r.valor_b <= 6


def test_detecta_par():
    r = ResultadoDados(valor_a=3, valor_b=3)
    assert r.es_par
    assert r.suma == 6


def test_detecta_no_par():
    r = ResultadoDados(valor_a=3, valor_b=5)
    assert not r.es_par


def test_detecta_par_de_seises():
    r = ResultadoDados(valor_a=6, valor_b=6)
    assert r.es_par
    assert r.es_par_de_seises


# ============================================
# Tests: salida de cárcel
# ============================================

def test_no_puede_salir_sin_pares(motor, jugador_rojo):
    dados = ResultadoDados(valor_a=3, valor_b=5)
    assert not motor.puede_sacar_de_carcel(jugador_rojo, dados)


def test_puede_salir_con_pares(motor, jugador_rojo):
    dados = ResultadoDados(valor_a=3, valor_b=3)
    assert motor.puede_sacar_de_carcel(jugador_rojo, dados)


def test_no_puede_salir_si_no_hay_fichas_en_carcel(motor, jugador_rojo, tablero):
    # Vaciar la cárcel
    for f in list(jugador_rojo.fichas):
        tablero.colocar_en_casilla(f, SALIDA_POR_COLOR["rojo"])
    dados = ResultadoDados(valor_a=4, valor_b=4)
    assert not motor.puede_sacar_de_carcel(jugador_rojo, dados)


def test_sacar_de_carcel_lleva_a_casilla_salida(motor, jugador_rojo, tablero):
    dados = ResultadoDados(valor_a=2, valor_b=2)
    resultado = motor.sacar_de_carcel(tablero, jugador_rojo, dados)
    assert resultado.exito
    assert resultado.salio_de_carcel
    ficha_movida = tablero.get_ficha_por_id(resultado.ficha_movida)
    assert ficha_movida.estado == ESTADO_TABLERO
    assert ficha_movida.posicion == SALIDA_POR_COLOR["rojo"]


# ============================================
# Tests: oportunidades iniciales
# ============================================

def test_oportunidades_iniciales_son_3(jugador_rojo):
    assert jugador_rojo.oportunidades_salida == OPORTUNIDADES_SALIDA_INICIAL


def test_consumir_oportunidad_decrementa(motor, jugador_rojo):
    motor.consumir_oportunidad_salida(jugador_rojo)
    assert jugador_rojo.oportunidades_salida == 2
    motor.consumir_oportunidad_salida(jugador_rojo)
    motor.consumir_oportunidad_salida(jugador_rojo)
    assert jugador_rojo.oportunidades_salida == 0


def test_oportunidades_no_bajan_de_cero(motor, jugador_rojo):
    for _ in range(10):
        motor.consumir_oportunidad_salida(jugador_rojo)
    assert jugador_rojo.oportunidades_salida == 0


# ============================================
# Tests: regla de los pares consecutivos
# ============================================

def test_par_incrementa_contador(motor, jugador_rojo):
    dados = ResultadoDados(valor_a=2, valor_b=2)
    motor.procesar_pares(jugador_rojo, dados)
    assert jugador_rojo.pares_consecutivos == 1


def test_no_par_resetea_contador(motor, jugador_rojo):
    dados_par = ResultadoDados(valor_a=2, valor_b=2)
    motor.procesar_pares(jugador_rojo, dados_par)
    motor.procesar_pares(jugador_rojo, dados_par)
    assert jugador_rojo.pares_consecutivos == 2

    dados_no_par = ResultadoDados(valor_a=2, valor_b=5)
    motor.procesar_pares(jugador_rojo, dados_no_par)
    assert jugador_rojo.pares_consecutivos == 0


def test_tres_pares_consecutivos_devuelve_saca_ficha(motor, jugador_rojo):
    dados = ResultadoDados(valor_a=3, valor_b=3)
    motor.procesar_pares(jugador_rojo, dados)
    motor.procesar_pares(jugador_rojo, dados)
    resultado = motor.procesar_pares(jugador_rojo, dados)
    assert resultado["saca_ficha"] is True


def test_par_normal_retiene_turno(motor, jugador_rojo):
    dados = ResultadoDados(valor_a=4, valor_b=4)
    resultado = motor.procesar_pares(jugador_rojo, dados)
    assert resultado["saca_ficha"] is False
    assert resultado["retiene_turno"] is True


def test_no_par_no_retiene_turno(motor, jugador_rojo):
    dados = ResultadoDados(valor_a=4, valor_b=2)
    resultado = motor.procesar_pares(jugador_rojo, dados)
    assert resultado["retiene_turno"] is False


def test_quemar_ficha_la_lleva_a_meta(motor, jugador_rojo, tablero):
    # Sacar una ficha al tablero
    ficha = jugador_rojo.fichas[0]
    tablero.colocar_en_casilla(ficha, 10)
    resultado = motor.quemar_ficha(tablero, jugador_rojo, ficha.id)
    assert resultado.exito
    assert resultado.llego_a_meta
    ficha_final = tablero.get_ficha_por_id(ficha.id)
    assert ficha_final.estado == ESTADO_META


def test_no_se_puede_quemar_ficha_en_carcel(motor, jugador_rojo, tablero):
    ficha = jugador_rojo.fichas[0]
    # Ya está en cárcel por la fixture
    resultado = motor.quemar_ficha(tablero, jugador_rojo, ficha.id)
    assert not resultado.exito


# ============================================
# Tests: movimientos legales
# ============================================

def test_no_hay_movimientos_si_todas_fichas_en_carcel(motor, jugador_rojo, tablero):
    dados = ResultadoDados(valor_a=3, valor_b=5)  # No es par, no puede salir
    movs = motor.calcular_movimientos_legales(tablero, jugador_rojo, dados)
    assert len(movs) == 0


def test_movimiento_normal_en_tablero(motor, jugador_rojo, tablero):
    ficha = jugador_rojo.fichas[0]
    tablero.colocar_en_casilla(ficha, 10)
    dados = ResultadoDados(valor_a=3, valor_b=2)
    movs = motor.calcular_movimientos_legales(tablero, jugador_rojo, dados)
    # Debe poder moverse con el dado A (3), B (2) o la suma (5)
    assert len(movs) >= 3
    # Verificar que una de las opciones lleva a casilla 13
    valores = {m.valor for m in movs}
    assert 3 in valores
    assert 2 in valores
    assert 5 in valores


# ============================================
# Tests: aplicar movimiento y captura
# ============================================

def test_aplicar_movimiento_simple(motor, jugador_rojo, tablero):
    ficha = jugador_rojo.fichas[0]
    tablero.colocar_en_casilla(ficha, 10)
    resultado = motor.aplicar_movimiento(tablero, jugador_rojo, ficha.id, 5)
    assert resultado.exito
    f_final = tablero.get_ficha_por_id(ficha.id)
    assert f_final.posicion == 15


def test_captura_ficha_rival(motor, jugador_rojo, jugador_azul, tablero):
    # Ficha roja en 10
    f_rojo = jugador_rojo.fichas[0]
    tablero.colocar_en_casilla(f_rojo, 10)
    # Ficha azul en 15 (no seguro)
    f_azul = jugador_azul.fichas[0]
    tablero.colocar_en_casilla(f_azul, 15)
    # Mover roja 5 pasos -> aterriza en 15 y captura
    resultado = motor.aplicar_movimiento(tablero, jugador_rojo, f_rojo.id, 5)
    assert resultado.exito
    assert f_azul.id in resultado.fichas_capturadas
    # Verificar que la azul está en cárcel
    f_azul_final = tablero.get_ficha_por_id(f_azul.id)
    assert f_azul_final.estado == ESTADO_CARCEL


def test_no_captura_en_seguro(motor, jugador_rojo, jugador_azul, tablero):
    # Casilla 12 es seguro
    f_azul = jugador_azul.fichas[0]
    tablero.colocar_en_casilla(f_azul, 12)
    f_rojo = jugador_rojo.fichas[0]
    tablero.colocar_en_casilla(f_rojo, 9)  # 9 + 3 = 12
    resultado = motor.aplicar_movimiento(tablero, jugador_rojo, f_rojo.id, 3)
    assert resultado.exito
    assert len(resultado.fichas_capturadas) == 0
    # La azul sigue en 12
    f_azul_final = tablero.get_ficha_por_id(f_azul.id)
    assert f_azul_final.posicion == 12
    assert f_azul_final.estado == ESTADO_TABLERO


# ============================================
# Tests: recta final y victoria
# ============================================

def test_entrar_a_recta_final(motor, jugador_rojo, tablero):
    # Para rojo, la entrada a la recta es la casilla 68
    f = jugador_rojo.fichas[0]
    tablero.colocar_en_casilla(f, 66)
    # 66 + 4 = entra a recta posición 2
    resultado = motor.aplicar_movimiento(tablero, jugador_rojo, f.id, 4)
    assert resultado.exito
    f_final = tablero.get_ficha_por_id(f.id)
    assert f_final.estado == ESTADO_RECTA_FINAL
    assert f_final.posicion == 2


def test_llegar_a_meta_desde_recta(motor, jugador_rojo, tablero):
    f = jugador_rojo.fichas[0]
    tablero.colocar_en_recta(f, 5)  # En recta posición 5
    # 5 + 3 = 8 -> llega a meta
    resultado = motor.aplicar_movimiento(tablero, jugador_rojo, f.id, 3)
    assert resultado.exito
    assert resultado.llego_a_meta


def test_no_pasarse_de_meta(motor, jugador_rojo, tablero):
    f = jugador_rojo.fichas[0]
    tablero.colocar_en_recta(f, 7)  # En recta posición 7
    # 7 + 3 = 10, se pasa
    resultado = motor.aplicar_movimiento(tablero, jugador_rojo, f.id, 3)
    assert not resultado.exito


def test_victoria_cuando_4_fichas_en_meta(motor, jugador_rojo, tablero):
    for f in jugador_rojo.fichas:
        tablero.colocar_en_meta(f)
    assert jugador_rojo.ha_ganado()
    ganador = motor.hay_ganador([jugador_rojo])
    assert ganador is jugador_rojo


def test_no_victoria_con_3_fichas(motor, jugador_rojo, tablero):
    for f in jugador_rojo.fichas[:3]:
        tablero.colocar_en_meta(f)
    # La cuarta sigue en cárcel
    assert not jugador_rojo.ha_ganado()
    assert motor.hay_ganador([jugador_rojo]) is None


# ============================================
# Tests: tablero - serialización
# ============================================

def test_tablero_to_dict_es_serializable(jugador_rojo, tablero):
    f = jugador_rojo.fichas[0]
    tablero.colocar_en_casilla(f, 23)
    import json
    d = tablero.to_dict()
    # Si esto no lanza excepción, es serializable
    json.dumps(d)


# ============================================
# Tests: gestor de turnos
# ============================================

def test_primer_turno_es_mayor_tirada():
    from game_server.motor.gestor_turnos import GestorTurnos
    gestor = GestorTurnos()
    j1 = Jugador(id=1, username="a", color="rojo")
    j2 = Jugador(id=2, username="b", color="azul")
    j3 = Jugador(id=3, username="c", color="verde")
    gestor.registrar_tirada_inicial(1, 6)
    gestor.registrar_tirada_inicial(2, 11)
    gestor.registrar_tirada_inicial(3, 8)
    gestor.determinar_primer_turno([j1, j2, j3])
    assert gestor.jugador_actual_id() == 2  # mayor tirada


def test_avanzar_turno_es_circular():
    from game_server.motor.gestor_turnos import GestorTurnos
    gestor = GestorTurnos()
    j1 = Jugador(id=1, username="a", color="rojo")
    j2 = Jugador(id=2, username="b", color="azul")
    gestor.registrar_tirada_inicial(1, 6)
    gestor.registrar_tirada_inicial(2, 4)
    gestor.determinar_primer_turno([j1, j2])
    assert gestor.jugador_actual_id() == 1
    gestor.avanzar_turno()
    assert gestor.jugador_actual_id() == 2
    gestor.avanzar_turno()
    assert gestor.jugador_actual_id() == 1
