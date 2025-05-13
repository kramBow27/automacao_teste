from automacao_copia import new_driver
from .driver import build
from .scraper import (
    _url_lista,
    _espera_links,
    busca_beneficiarios,
    mapea_beneficiario,
    _snapshot,
    salva_evidencia,
)
import logging, json
from pathlib import Path

log = logging.getLogger("rpa")


def run(query: Optional[str], visible: bool = False):
    """
    Executa a coleta completa de até 10 beneficiários para a `query` informada.
    """
    driver = new_driver(visible)
    try:
        beneficiarios = []
        for b in busca_beneficiarios(driver, query):
            try:
                beneficiarios.append(mapea_beneficiario(driver, b))
            except Exception as e:
                logger.error("Erro no beneficiário %s: %s", b, e)
                salva_evidencia(driver, "beneficiario")
        return {"consulta": query, "beneficiarios": beneficiarios}
    finally:
        driver.quit()
