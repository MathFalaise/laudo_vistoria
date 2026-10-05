"""
MOTOR do laudo de vistoria — camada compartilhada pelo CLI e pela aplicação web.

Regra de ouro deste pacote (pedido do vistoriador, 25/09/2026): existe UM
motor só. O CLI (`main.py`, `validar.py`, `conferir.py`, `revisar.py`) e a API
web chamam exatamente estas funções. Nada de "lógica A" no CLI e "lógica B" na
web — comportamentos diferentes no mesmo laudo seriam pior que não ter web.

Os módulos na raiz do repositório com estes mesmos nomes (`config.py`,
`report_writer.py`, ...) são apenas ALIASES deste pacote, mantidos para os
scripts e para quem já tinha comandos salvos.
"""
