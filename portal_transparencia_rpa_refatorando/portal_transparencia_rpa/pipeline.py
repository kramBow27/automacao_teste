from typing import Optional

from . import scraper, constants
from .driver import build as new_driver
from .scraper import (
    busca_beneficiarios,
    mapea_beneficiario,
    salva_evidencia,
)
import logging, json
from pathlib import Path

logger = logging.getLogger("rpa")


def run(query: Optional[str], visible: bool = False, base_dir: Path | None = None):
    """
    Executa a coleta completa de até 10 beneficiários para a `query` informada.
    """
    driver = new_driver(visible)
    constants.RUN_DIR = base_dir
    scraper.RUN_DIR = base_dir
    try:
        beneficiarios = []
        for b in busca_beneficiarios(driver, query):
            try:
                beneficiarios.append(mapea_beneficiario(driver, b))
            except Exception as e:
                logger.error("Erro no beneficiário %s: %s", b, e)
                salva_evidencia(driver, "beneficiario", base_dir)
        return {"consulta": query, "beneficiarios": beneficiarios}
    finally:
        driver.quit()
