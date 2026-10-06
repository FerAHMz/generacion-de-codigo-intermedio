import os
import sys

# Permite ejecutar `pytest` desde la raíz sin instalar el paquete.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
