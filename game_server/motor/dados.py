"""
Dados del juego.

Encapsula el lanzamiento de los dos dados y la detección de pares.
"""

import random
from dataclasses import dataclass


@dataclass
class ResultadoDados:
    valor_a: int
    valor_b: int

    @property
    def es_par(self) -> bool:
        return self.valor_a == self.valor_b

    @property
    def suma(self) -> int:
        return self.valor_a + self.valor_b

    @property
    def es_par_de_seises(self) -> bool:
        return self.valor_a == 6 and self.valor_b == 6

    def to_dict(self) -> dict:
        return {
            "valor_a": self.valor_a,
            "valor_b": self.valor_b,
            "es_par": self.es_par,
            "suma": self.suma,
        }


class Dados:
    """
    Encapsula el lanzamiento de dados.

    Permite inyectar un generador de aleatoriedad para tests reproducibles.
    """

    def __init__(self, seed: int | None = None):
        self._random = random.Random(seed) if seed is not None else random

    def lanzar(self) -> ResultadoDados:
        a = self._random.randint(1, 6)
        b = self._random.randint(1, 6)
        return ResultadoDados(valor_a=a, valor_b=b)

    def lanzar_forzado(self, valor_a: int, valor_b: int) -> ResultadoDados:
        """Usado en tests para forzar un resultado específico."""
        if not (1 <= valor_a <= 6) or not (1 <= valor_b <= 6):
            raise ValueError("Los valores de los dados deben estar entre 1 y 6")
        return ResultadoDados(valor_a=valor_a, valor_b=valor_b)
