"""
Constantes del motor de parqués.

El tablero estándar de parqués colombiano (4 jugadores) tiene:
- 68 casillas en el recorrido principal (numeradas 1-68)
- 4 cárceles (una por color)
- 4 rectas finales (una por color, 8 casillas cada una hacia la meta)
- 4 salidas (casilla por donde sale cada color al tablero)
- 12 casillas de seguro distribuidas
"""

# === Colores válidos ===
COLORES = ["rojo", "azul", "verde", "amarillo"]

# === Casillas de salida por color ===
# Cuando un jugador saca una ficha de la cárcel, va a esta casilla
SALIDA_POR_COLOR = {
    "rojo": 5,
    "azul": 22,
    "amarillo": 39,
    "verde": 56,
}

# === Entrada a la recta final por color ===
# La última casilla del recorrido antes de entrar a la recta final
ENTRADA_RECTA_FINAL = {
    "rojo": 68,
    "azul": 17,
    "amarillo": 34,
    "verde": 51,
}

# === Casillas seguras del tablero ===
# Incluyen las salidas (que también son seguras) y otras casillas marcadas
CASILLAS_SEGURAS = {
    # Salidas (son seguras)
    5, 22, 39, 56,
    # Seguros adicionales (12 + 4 = 16 especiales según el enunciado)
    12, 17, 29, 34, 46, 51, 63, 68,
    # Adicionales para llegar a 12 seguros
    9, 26, 43, 60,
}

# === Tamaño de la recta final ===
RECTA_FINAL_LONGITUD = 8  # 8 casillas hasta la meta

# === Número de fichas por jugador ===
FICHAS_POR_JUGADOR = 4

# === Estados de una ficha ===
ESTADO_CARCEL = "carcel"
ESTADO_TABLERO = "tablero"
ESTADO_RECTA_FINAL = "recta_final"
ESTADO_META = "meta"

# === Configuración de reglas ===
OPORTUNIDADES_SALIDA_INICIAL = 3      # 3 turnos iniciales para salir con par
PARES_CONSECUTIVOS_LIMITE = 3         # 3 pares seguidos = sacar ficha
TOTAL_CASILLAS_TABLERO = 68


def es_seguro(casilla: int) -> bool:
    """Devuelve True si la casilla es de seguro (no se puede capturar)."""
    return casilla in CASILLAS_SEGURAS


def siguiente_casilla(casilla_actual: int, pasos: int) -> int:
    """
    Calcula la siguiente casilla del recorrido principal.
    El tablero es circular: después de la 68 sigue la 1.
    """
    return ((casilla_actual - 1 + pasos) % TOTAL_CASILLAS_TABLERO) + 1
