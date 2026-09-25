"""Alias de compatibilidade: o módulo real é core/report_writer.py.

O motor foi para o pacote `core` em 25/09/2026, na evolução para aplicação
web. Este arquivo existe para que `import report_writer` continue funcionando nos
scripts de linha de comando e em qualquer coisa que já apontasse para cá — e
faz isso apontando para o MESMO objeto de módulo, não para uma cópia, de modo
que não há como as duas versões divergirem.
"""

import sys

from core import report_writer as _modulo_real

sys.modules[__name__] = _modulo_real
