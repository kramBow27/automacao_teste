"""RPA Bot – Portal da Transparência  v1.8
────────────────────────────────────────────────────────────────────────

"""

from __future__ import annotations
import argparse, json, logging, re, sys, time, traceback, uuid
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlencode

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as W
from selenium.webdriver.support import expected_conditions as EC

# ───────────── constantes ─────────────
BASE = "https://portaldatransparencia.gov.br"
LIST_ENDPOINT = f"{BASE}/pessoa-fisica/busca/lista"
anchor_rx = re.compile(
    r'href="(/busca/pessoa-fisica/[^"]+)"[^>]*class="link-busca-nome"'
)


# ───────────── logger ─────────────
def setup_logger(show_console=False):
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


# ───────────── evidência ─────────────
def save_evidence(driver: webdriver.Chrome, prefix: str):
    uid = uuid.uuid4().hex[:8]
    html = Path(f"error-{prefix}-{uid}.html")
    png = Path(f"error-{prefix}-{uid}.png")
    html.write_text(driver.page_source, encoding="utf-8")
    driver.save_screenshot(str(png))
    logger.error("Evidência salva: %s  %s", html.name, png.name)


# ───────────── webdriver ─────────────
def new_driver(visible=False):
    opt = Options()
    if not visible:
        opt.add_argument("--headless=new")
    opt.add_argument("--window-size=1920,1080")
    opt.add_argument("--disable-gpu")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-blink-features=AutomationControlled")
    opt.add_argument("--lang=pt-BR")
    opt.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    return webdriver.Chrome(options=opt)  # Selenium Manager resolve o driver


# ───────────── pequenas utilidades ─────────────
def wait_dom(driver: webdriver.Chrome, timeout=20):
    """Bloqueia até document.readyState == 'complete'."""
    W(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def build_list_url(q: Optional[str]) -> str:
    p = {"pagina": 1, "tamanhoPagina": 10, "beneficiarioProgramaSocial": "true"}
    if q:
        p["termo"] = q
    return f"{LIST_ENDPOINT}?{urlencode(p, quote_via=quote_plus)}"


# ───────────── scraping ─────────────
def wait_for_results(driver: webdriver.Chrome, timeout=30) -> List[str]:
    wait_dom(driver)
    end = time.time() + timeout
    while time.time() < end:
        links = driver.find_elements(By.CSS_SELECTOR, "#resultados a.link-busca-nome")
        if links:
            return [a.get_attribute("href") for a in links]
        time.sleep(1)
    # fallback - regex
    return [BASE + h for h in anchor_rx.findall(driver.page_source)]


def search_people(driver: webdriver.Chrome, query: Optional[str]) -> List[str]:
    url = build_list_url(query)
    logger.info("Abrindo lista: %s", url)
    driver.get(url)
    links = wait_for_results(driver)
    if not links:
        save_evidence(driver, "list")
        raise RuntimeError("Nenhum resultado encontrado.")
    uniq = list(dict.fromkeys(links))  # remove duplicatas preservando ordem
    logger.info("Coletados %d links", len(uniq))
    return uniq[:10]


def get_text(driver: webdriver.Chrome, label: str) -> str:
    try:
        xp = f"//strong[normalize-space()='{label}']/following-sibling::span"
        return driver.find_element(By.XPATH, xp).text.strip()
    except NoSuchElementException:
        return ""


def parse_benefit(driver: webdriver.Chrome, url: str) -> Dict:
    driver.get(url)
    wait_dom(driver)
    # espera a tabela aparecer (máx 15s)
    try:
        W(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
        )
    except TimeoutException:
        logger.warning("Tabela de parcelas não apareceu em %s", url)
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
    wait_dom(driver)
    person = {
        "nome": get_text(driver, "Nome"),
        "cpf": get_text(driver, "CPF"),
        "localidade": get_text(driver, "Localidade"),
        "screenshot": driver.get_screenshot_as_base64(),
        "beneficios": [],
    }
    # botões "Detalhar" dentro do accordion
    buttons = driver.find_elements(
        By.CSS_SELECTOR, "#accordion-recebimentos-recursos a.br-button.secondary"
    )
    for btn in buttons:
        person["beneficios"].append(parse_benefit(driver, btn.get_attribute("href")))
    return person


# ───────────── runner ─────────────
def run(query: Optional[str], visible=False):
    d = new_driver(visible)
    try:
        urls = search_people(d, query)
        pessoas = []
        for u in urls:
            try:
                pessoas.append(parse_person(d, u))
            except Exception as e:
                logger.error("Erro na pessoa %s: %s", u, e)
                save_evidence(d, "person")
        return {"consulta": query or "*primeiros 10*", "pessoas": pessoas}
    finally:
        d.quit()


# ───────────── CLI ─────────────
def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="", help="Filtro (Nome, CPF ou NIS)")
    ap.add_argument("--out", default="resultado.json", help="Arquivo JSON de saída")
    ap.add_argument("--visible", action="store_true", help="Mostra navegador")
    ap.add_argument("--debug", action="store_true", help="Logs no console")
    args = ap.parse_args()

    global logger
    logger = setup_logger(args.debug)
    try:
        data = run(args.query.strip() or None, visible=args.visible)
        Path(args.out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("✔ Salvo em %s", args.out)
    except Exception as e:
        logger.error("Falha: %s", e)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli()
