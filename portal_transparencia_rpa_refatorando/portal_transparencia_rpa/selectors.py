"""
Seletores reutilizados em mais de um módulo.
Manter num arquivo separado facilita manutenção e evita strings soltas.
"""

import re

# Regex para extrair links de beneficiários da listagem
anchor_rx = re.compile(
    r'href="(/busca/pessoa-fisica/[^"]+)"[^>]*class="link-busca-nome"'
)

# Outros seletores que possam ser úteis no futuro podem ser adicionados aqui, por
# exemplo:
# CARD_SELECTOR      = "#accordion-recebimentos-recursos div.br-table div.responsive"
# ACCORDION_HEADER   = "button.header[aria-controls='accordion-recebimentos-recursos']"
# ACCORDION_TABLE    = "#accordion-recebimentos-recursos div.br-table"
