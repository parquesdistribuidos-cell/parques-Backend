"""
Constantes del motor de parqués.

El tablero estándar de parqués colombiano (4 jugadores) tiene:
- 68 casillas en el recorrido principal (numeradas 1-68)
- 4 cárceles (una por color)
- 4 rectas finales (una por color, 8 casillas cada una hacia la meta)
- 4 salidas (casilla por donde sale cada color al tablero)
- casillas de seguro distribuidas
"""

# === Colores válidos ===
COLORES = ["rojo", "azul", "verde", "amarillo"]

# === Casillas de salida por color ===
# Cuando un jugador saca una ficha de la cárcel, va a esta casilla
  
SALIDA_POR_COLOR = {
    "rojo": 43,
    "azul": 60,
    "amarillo": 9,
    "verde": 26,
}

# === Entrada a la recta final por color ===
# La última casilla del recorrido antes de entrar a la recta final
ENTRADA_RECTA_FINAL = {
    "rojo": 38,
    "azul": 55,
    "amarillo": 4,
    "verde": 21,
}

# === Casillas seguras del tablero ===
# Incluyen las salidas (que también son seguras) y otras casillas marcadas
CASILLAS_SEGURAS = {
    21, 26, 33, 38, 43, 50, 55, 60, 67, 4, 9, 16
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
