"""Alias de compatibilidade: o módulo real é core/style_guide.py.

O motor foi para o pacote `core` em 25/09/2026, na evolução para aplicação
web. Este arquivo existe para que `import style_guide` continue funcionando nos
scripts de linha de comando e em qualquer coisa que já apontasse para cá — e
faz isso apontando para o MESMO objeto de módulo, não para uma cópia, de modo
que não há como as duas versões divergirem.
"""

import sys

from core import style_guide as _modulo_real

sys.modules[__name__] = _modulo_real
