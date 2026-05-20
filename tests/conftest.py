"""
Configuración global de pytest. Asegura que game_server sea importable.
"""
import sys
from pathlib import Path

# Agregamos backend/ al path para que `from game_server.motor...` funcione
sys.path.insert(0, str(Path(__file__).parent.parent))
