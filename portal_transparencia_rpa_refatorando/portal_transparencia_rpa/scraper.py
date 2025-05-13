"""
Scraper principal para o Portal da Transparência.
Mantém exatamente as mesmas funções, nomes e comentários do código original,
apenas extraindo variáveis fixas para `constants.py` e a regex para `selectors.py`.
"""

import json, logging, re, sys, time, uuid
from pathlib import Path
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as W
from selenium.webdriver.support import expected_conditions as EC

# ---- módulos do próprio projeto -------------------------------------------
from .driver import build as new_driver  # cria o ChromeDriver
from .constants import BASE, LIST_ENDPOINT, COLUNAS, PATH_JSON
from .selectors import anchor_rx
# ----------------------------------------------------------------------------

logger = logging.getLogger("rpa")


# --------------------------------------------------------------------------- #
# Utilidades                                                                  #
# --------------------------------------------------------------------------- #


def espera_dom(driver: webdriver.Chrome, timeout: int = 20):
    """Espera o DOM carregar completamente (document.readyState == 'complete')."""
    W(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def espera_resultados(driver: webdriver.Chrome, timeout: int = 30) -> List[str]:
    """Espera aparecerem os links de beneficiários na lista de resultados."""
    espera_dom(driver)
    fim = time.time() + timeout
    while time.time() < fim:
        links = driver.find_elements(By.CSS_SELECTOR, "#resultados a.link-busca-nome")
        if links:
            return [
                a.get_attribute("href") or "" for a in links if a.get_attribute("href")
            ]
        time.sleep(1)
    # fallback via regex, se o CSS não achou nada
    return [BASE + h for h in anchor_rx.findall(driver.page_source)]


def url_lista_beneficiarios(query: Optional[str]):
    """Monta a URL da lista de beneficiários (até 10 por página)."""
    from urllib.parse import quote_plus, urlencode

    params = {
        "pagina": 1,
        "tamanhoPagina": 10,
        "beneficiarioProgramaSocial": "true",
    }
    if query:
        params["termo"] = query
    return f"{LIST_ENDPOINT}?{urlencode(params, quote_via=quote_plus)}"


def salva_evidencia(driver: webdriver.Chrome, prefixo: str):
    """Salva HTML + screenshot para debug."""
    uid = uuid.uuid4().hex[:8]
    Path(f"{prefixo}_{uid}.html").write_text(driver.page_source, encoding="utf-8")
    driver.save_screenshot(f"{prefixo}_{uid}.png")
    logger.info("Evidência salva: %s_%s", prefixo, uid)


def higienizar(txt: str) -> str:
    """Remove espaços/quebras de linha duplicados."""
    return re.sub(r"\s+", " ", txt or "").strip()


# --------------------------------------------------------------------------- #
# Navegação / scraping                                                        #
# --------------------------------------------------------------------------- #


def busca_beneficiarios(driver: webdriver.Chrome, query: Optional[str]):
    """Retorna (máx. 10) links de beneficiários para a pesquisa fornecida."""
    driver.get(url_lista_beneficiarios(query))
    links = espera_resultados(driver)
    if not links:
        salva_evidencia(driver, "erro_lista")
        raise RuntimeError("Nenhum beneficiário encontrado")

    salva_evidencia(driver, "sucesso_lista")
    # remove duplicados preservando ordem
    return list(dict.fromkeys(links))[:10]


def get_texto(driver: webdriver.Chrome, label: str) -> str:
    """Extrai o texto de um campo exibido na ficha do beneficiário."""
    xp = f"//strong[normalize-space()='{label}']/following-sibling::span"
    try:
        return driver.find_element(By.XPATH, xp).text.strip()
    except NoSuchElementException:
        return ""


def abrir_beneficios(driver: webdriver.Chrome, timeout: int = 10):
    """Expande o accordion de recebimentos."""
    header = driver.find_element(
        By.CSS_SELECTOR,
        "button.header[aria-controls='accordion-recebimentos-recursos']",
    )
    try:
        if "active" not in (header.get_attribute("class") or ""):
            header.click()
    except ElementClickInterceptedException:
        # fecha cookiebar e tenta de novo
        try:
            driver.find_element(By.ID, "cookiebar_close").click()
            header.click()
        except Exception:
            pass

    W(driver, timeout).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#accordion-recebimentos-recursos div.br-table")
        )
    )


def fetch_parcelas_json(
    driver: webdriver.Chrome,
    segmento: str,
    sk_beneficiario: str,
    pessoa_id: str,
) -> List[Dict]:
    """
    Usa os cookies do Selenium para chamar o endpoint JSON
    e devolve a lista de parcelas já no formato esperado.
    """
    path = (
        PATH_JSON.get(segmento, "sacado/resultado")
        if segmento != "safra"
        else "recebido/resultado"
    )
    url = f"{BASE}/beneficios/{segmento}/{path}"

    params = {
        "paginacaoSimples": "true",
        "tamanhoPagina": 1000,
        "offset": 0,
        "direcaoOrdenacao": "desc",
        "colunaOrdenacao": "numeroParcela"
        if segmento == "auxilio-emergencial"
        else "mesReferencia",
        "colunasSelecionadas": COLUNAS[segmento],
        (
            "skBeneficiario"
            if segmento in ("auxilio-emergencial", "safra")
            else "beneficiario"
        ): sk_beneficiario,
        "pessoa": pessoa_id,
    }

    import requests

    sess = requests.Session()
    for ck in driver.get_cookies():
        sess.cookies.set(ck["name"], ck["value"])

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": driver.current_url,
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
    }

    resp = sess.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    out: List[Dict] = []
    for row in data:
        if segmento == "auxilio-emergencial":
            out.append(
                dict(
                    mes_disponibilizacao=higienizar(row["mesDisponibilizacao"]),
                    parcela=higienizar(row["numeroParcela"]),
                    uf=higienizar(row["uf"]),
                    municipio=higienizar(row["municipio"]),
                    enquadramento=higienizar(row["enquadramento"]),
                    valor=higienizar(row["valor"]),
                    observacao=higienizar(row["observacao"]),
                )
            )
        elif segmento == "auxilio-brasil":
            out.append(
                dict(
                    mes_folha=higienizar(row["mesFolha"]),
                    mes_ref=higienizar(row["mesReferencia"]),
                    uf=higienizar(row["uf"]),
                    municipio=higienizar(row["municipio"]),
                    valor=higienizar(row["valor"]),
                )
            )
        elif segmento == "bolsa-familia":
            out.append(
                dict(
                    mes_folha=higienizar(row["mesFolha"]),
                    mes_ref=higienizar(row["mesReferencia"]),
                    uf=higienizar(row["uf"]),
                    municipio=higienizar(row["municipio"]),
                    qtd_dependentes=higienizar(row["quantidadeDependentes"]),
                    valor=higienizar(row["valor"]),
                )
            )
        elif segmento == "novo-bolsa-familia":
            out.append(
                dict(
                    mes_folha=higienizar(row["mesFolha"]),
                    mes_ref=higienizar(row["mesReferencia"]),
                    uf=higienizar(row["uf"]),
                    municipio=higienizar(row["municipio"]),
                    valor=higienizar(row["valor"]),
                )
            )
        elif segmento == "safra":
            out.append(
                dict(
                    mes_folha=higienizar(row["mesFolha"]),
                    uf=higienizar(row["uf"]),
                    municipio=higienizar(row["municipio"]),
                    valor=higienizar(row["valor"]),
                )
            )
    return out


def coletar_cards(driver: webdriver.Chrome) -> List[dict]:
    """Coleta os cards exibidos dentro do accordion de recebimentos."""
    cards = []
    selector = "#accordion-recebimentos-recursos div.br-table div.responsive"
    for box in driver.find_elements(By.CSS_SELECTOR, selector):
        try:
            titulo = higienizar(
                box.find_element(By.TAG_NAME, "strong").get_attribute("textContent")
            )
            row = box.find_element(By.CSS_SELECTOR, "tbody tr")
            cols = [
                higienizar(td.get_attribute("textContent"))
                for td in row.find_elements(By.TAG_NAME, "td")
            ]
            href = row.find_element(By.CSS_SELECTOR, "a.br-button").get_attribute(
                "href"
            )
            cards.append(
                dict(
                    beneficio=titulo,
                    nis=cols[1] if len(cols) > 1 else "",
                    nome=cols[2] if len(cols) > 2 else "",
                    valor_recebido=cols[3] if len(cols) > 3 else "",
                    href=href,
                    parcelas=[],
                )
            )
        except Exception as e:
            logger.warning("Erro ao coletar card: %s", e)
    return cards


def mapea_beneficio(
    driver: webdriver.Chrome, url: str, beneficiario_id: str
) -> List[dict]:
    """Mapeia as parcelas de um benefício (JSON + fallback HTML)."""
    m = re.search(r"/beneficios/([^/]+)/(\d+)", url)
    segmento = m.group(1) if m else ""
    sk_beneficiario = m.group(2) if m else ""

    # 1º: tenta via JSON (mais rápido)
    try:
        return fetch_parcelas_json(driver, segmento, sk_beneficiario, beneficiario_id)
    except Exception as e:
        logger.warning("Erro ao coletar parcelas JSON: %s", e)

    # 2º: fallback raspando a tabela HTML
    driver.get(url)
    espera_dom(driver)
    W(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
    )

    parcelas: List[Dict] = []
    for tr in driver.find_elements(By.CSS_SELECTOR, "table tbody tr"):
        tds = tr.find_elements(By.TAG_NAME, "td")
        if segmento == "auxilio-brasil" and len(tds) >= 5:
            parcelas.append(
                dict(
                    mes_folha=higienizar(tds[0].text),
                    mes_ref=higienizar(tds[1].text),
                    uf=higienizar(tds[2].text),
                    municipio=higienizar(tds[3].text),
                    valor=higienizar(tds[4].text),
                )
            )
        elif segmento == "auxilio-emergencial" and len(tds) >= 7:
            parcelas.append(
                dict(
                    mes_disponibilizacao=higienizar(tds[0].text),
                    parcela=higienizar(tds[1].text),
                    uf=higienizar(tds[2].text),
                    municipio=higienizar(tds[3].text),
                    enquadramento=higienizar(tds[4].text),
                    valor=higienizar(tds[5].text),
                    observacao=higienizar(tds[6].text),
                )
            )
        elif segmento == "bolsa-familia" and len(tds) >= 6:
            parcelas.append(
                dict(
                    mes_folha=higienizar(tds[0].text),
                    mes_ref=higienizar(tds[1].text),
                    uf=higienizar(tds[2].text),
                    municipio=higienizar(tds[3].text),
                    qtd_dependentes=higienizar(tds[4].text),
                    valor=higienizar(tds[5].text),
                )
            )
        elif segmento == "novo-bolsa-familia" and len(tds) >= 5:
            parcelas.append(
                dict(
                    mes_folha=higienizar(tds[0].text),
                    mes_ref=higienizar(tds[1].text),
                    uf=higienizar(tds[2].text),
                    municipio=higienizar(tds[3].text),
                    valor=higienizar(tds[4].text),
                )
            )
        elif segmento == "safra" and len(tds) >= 4:
            parcelas.append(
                dict(
                    mes_folha=higienizar(tds[0].text),
                    uf=higienizar(tds[1].text),
                    municipio=higienizar(tds[2].text),
                    valor=higienizar(tds[3].text),
                )
            )
    return parcelas


def mapea_beneficiario(driver: webdriver.Chrome, url: str):
    """Coleta dados do beneficiário + benefícios / parcelas."""
    logger.info("Processando beneficiário %s", url)
    driver.get(url)
    espera_dom(driver)

    beneficiario_match = re.search(r"/pessoa-fisica/(\d+)-", url)
    beneficiario_id = beneficiario_match.group(1) if beneficiario_match else ""

    beneficiario = dict(
        nome=get_texto(driver, "Nome"),
        cpf=get_texto(driver, "CPF"),
        localidade=get_texto(driver, "Localidade"),
        screenshot=driver.get_screenshot_as_base64(),
        beneficios=[],
    )

    abrir_beneficios(driver)
    cards = coletar_cards(driver)
    ficha_url = driver.current_url

    for card in cards:
        try:
            card["parcelas"] = mapea_beneficio(driver, card["href"], beneficiario_id)
        except Exception as e:
            logger.error("Erro no benefício %s: %s", card.get("href"), e)
            salva_evidencia(driver, "beneficio")
        finally:
            driver.get(ficha_url)
            espera_dom(driver)
            abrir_beneficios(driver)

    beneficiario["beneficios"] = cards
    return beneficiario


# --------------------------------------------------------------------------- #
# Orquestração high-level (ponto de entrada)                                  #
# --------------------------------------------------------------------------- #


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
