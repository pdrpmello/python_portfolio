"""Pacote de testes: põe src/ no sys.path para achar os módulos de runtime."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
