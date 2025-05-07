"""RPA Bot – Portal da Transparência  v1.7
════════════════════════════════════
* **Compatível com qualquer versão do Chrome**: usa o Selenium Manager
  (Selenium ≥ 4.18) para baixar e gerenciar automaticamente o ChromeDriver.
* Estratégia de coleta da lista, evidências e logging iguais à versão 1.6.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import traceback
import uuid
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlencode

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE = "https://portaldatransparencia.gov.br"
LIST_ENDPOINT = f"{BASE}/pessoa-fisica/busca/lista"

anchor_rx = re.compile(
    r"href=\"(/busca/pessoa-fisica/[^\"]+)\"[^>]*class=\"link-busca-nome\""
)

# ---------------------------------------------------------------------------
# Logger helper
# ---------------------------------------------------------------------------


def setup_logger(show_console: bool):
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    lg = logging.getLogger("rpa")
    lg.setLevel(logging.DEBUG)
    lg.handlers.clear()
    fh = logging.FileHandler("rpa_bot.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt))
    lg.addHandler(fh)
    if show_console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(fmt))
        lg.addHandler(ch)
    return lg


logger = setup_logger(False)

# ---------------------------------------------------------------------------
# Utilidades de evidência
# ---------------------------------------------------------------------------


def save_evidence(driver: webdriver.Chrome, prefix: str):
    uid = uuid.uuid4().hex[:8]
    html_path = f"error-{prefix}-{uid}.html"
    png_path = f"error-{prefix}-{uid}.png"
    try:
        with open(html_path, "w", encoding="utf-8") as fp:
            fp.write(driver.page_source)
        driver.save_screenshot(png_path)
        logger.error("Evidência salva: %s  %s", html_path, png_path)
    except Exception as e:
        logger.error("Falha ao salvar evidência: %s", e)


# ---------------------------------------------------------------------------
# WebDriver – compatível com qualquer Chrome
# ---------------------------------------------------------------------------


def new_driver(visible: bool = False) -> webdriver.Chrome:
    opts = Options()
    if not visible:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=pt-BR")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    # Selenium Manager cuidará de baixar / escolher o ChromeDriver correto.
    return webdriver.Chrome(options=opts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_list_url(query: Optional[str]) -> str:
    params = {
        "pagina": 1,
        "tamanhoPagina": 10,
        "beneficiarioProgramaSocial": "true",
    }
    if query:
        params["termo"] = query
    return f"{LIST_ENDPOINT}?{urlencode(params, quote_via=quote_plus)}"


# ---------------------------------------------------------------------------
# Scraping core
# ---------------------------------------------------------------------------


def wait_for_results(driver: webdriver.Chrome, timeout: int = 30) -> List[str]:
    driver.execute_script("return document.readyState")
    start = time.time()
    while time.time() - start < timeout:
        links = driver.find_elements(By.CSS_SELECTOR, "#resultados a.link-busca-nome")
        if links:
            return [a.get_attribute("href") for a in links]
        time.sleep(1)
    # Fallback: busca via regex no HTML
    matches = anchor_rx.findall(driver.page_source)
    return [BASE + href for href in matches]


def search_people(driver: webdriver.Chrome, query: Optional[str]) -> List[str]:
    url = build_list_url(query)
    logger.info("Abrindo lista: %s", url)
    driver.get(url)
    links = wait_for_results(driver)
    if not links:
        save_evidence(driver, "list")
        raise RuntimeError("Lista vazia ou não encontrada pelo fallback.")
    logger.info("Coletados %d links", len(links))
    return links[:10]


def get_text(driver: webdriver.Chrome, label: str) -> str:
    xp = f"//strong[normalize-space()='{label}']/following-sibling::span"
    try:
        return driver.find_element(By.XPATH, xp).text.strip()
    except NoSuchElementException:
        return ""


def parse_benefit(driver: webdriver.Chrome, url: str) -> Dict:
    driver.get(url)
    title = driver.find_element(By.TAG_NAME, "h2").text.split(" - ")[0].strip()
    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    parcelas = []
    for tr in rows:
        tds = tr.find_elements(By.TAG_NAME, "td")
        if len(tds) >= 7:
            parcelas.append(
                {
                    "mes": tds[0].text,
                    "parcela": tds[1].text,
                    "uf": tds[2].text,
                    "municipio": tds[3].text,
                    "enquadramento": tds[4].text,
                    "valor": tds[5].text,
                    "obs": tds[6].text,
                }
            )
    return {"beneficio": title, "parcelas": parcelas}


def parse_person(driver: webdriver.Chrome, url: str) -> Dict:
    logger.info("Processando pessoa: %s", url)
    driver.get(url)
    person = {
        "nome": get_text(driver, "Nome"),
        "cpf": get_text(driver, "CPF"),
        "localidade": get_text(driver, "Localidade"),
        "screenshot": driver.get_screenshot_as_base64(),
        "beneficios": [],
    }
    buttons = driver.find_elements(
        By.CSS_SELECTOR, "#accordion-recebimentos-recursos a.br-button.secondary"
    )
    for b in buttons:
        person["beneficios"].append(parse_benefit(driver, b.get_attribute("href")))
    return person


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run(query: Optional[str], visible: bool) -> Dict:
    driver = new_driver(visible)
    try:
        urls = search_people(driver, query)
        pessoas = []
        for u in urls:
            try:
                pessoas.append(parse_person(driver, u))
            except Exception as e:
                logger.error("Erro na pessoa %s: %s", u, e)
                save_evidence(driver, "person")
        return {"consulta": query or "*primeiros 10*", "pessoas": pessoas}
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="", help="Filtro (Nome, CPF ou NIS)")
    ap.add_argument("--out", default="resultado.json", help="Arquivo JSON de saída")
    ap.add_argument("--visible", action="store_true", help="Abre navegador visível")
    ap.add_argument("--debug", action="store_true", help="Mostra logs no console")
    args = ap.parse_args()

    global logger
    logger = setup_logger(args.debug)

    try:
        data = run(args.query.strip() or None, visible=args.visible)
        with open(args.out, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        logger.info("✔ Salvo em %s", args.out)
    except Exception as e:
        logger.error("Falha: %s", e)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli()
