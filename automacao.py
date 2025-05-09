# """
# RPA Bot – Portal da Transparência  v2.0
# ────────────────────────────────────────────────────────────────────────
# • Herda a lógica da v1.9 (pessoas → benefícios → parcelas).
# • Nome do benefício lido sempre do <strong>.
# • Coleta NIS / Nome / Valor direto da primeira (e única) linha da
#   tabela-resumo.
# • Varredura de 100 % das parcelas: segue clicando em “próximo” até a
#   seta ficar cinza.
# """

# from __future__ import annotations

# import argparse, json, logging, re, sys, time, traceback, uuid
# from pathlib import Path
# from typing import Dict, List, Optional
# from urllib.parse import quote_plus, urlencode

# from selenium import webdriver
# from selenium.common.exceptions import (
#     NoSuchElementException,
#     TimeoutException,
#     ElementClickInterceptedException,
# )
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait as W
# from selenium.webdriver.support import expected_conditions as EC

# # ───────────── constantes ─────────────
# BASE = "https://portaldatransparencia.gov.br"
# LIST_ENDPOINT = f"{BASE}/pessoa-fisica/busca/lista"
# anchor_rx = re.compile(
#     r'href="(/busca/pessoa-fisica/[^"]+)"[^>]*class="link-busca-nome"'
# )


# # ───────────── logger ─────────────
# def setup_logger(show_console: bool = False):
#     fmt = "%(asctime)s [%(levelname)s] %(message)s"
#     lg = logging.getLogger("rpa")
#     lg.setLevel(logging.DEBUG)
#     lg.handlers.clear()
#     fh = logging.FileHandler("rpa_bot.log", encoding="utf-8")
#     fh.setFormatter(logging.Formatter(fmt))
#     lg.addHandler(fh)
#     if show_console:
#         ch = logging.StreamHandler(sys.stdout)
#         ch.setFormatter(logging.Formatter(fmt))
#         lg.addHandler(ch)
#     return lg


# logger = setup_logger(False)


# # ───────────── webdriver ─────────────
# def new_driver(visible: bool = False):
#     opt = Options()
#     if not visible:
#         opt.add_argument("--headless=new")
#     opt.add_argument("--window-size=1920,1080")
#     opt.add_argument("--disable-gpu")
#     opt.add_argument("--no-sandbox")
#     opt.add_argument("--disable-blink-features=AutomationControlled")
#     opt.add_argument("--lang=pt-BR")
#     opt.add_argument(
#         "--user-agent="
#         "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
#         "(KHTML, like Gecko) Chrome/120 Safari/537.36"
#     )
#     return webdriver.Chrome(options=opt)  # Selenium Manager resolve o driver


# # ───────────── helpers ─────────────
# def wait_dom(driver: webdriver.Chrome, timeout: int = 20):
#     """aguarda carregamento completo do DOM"""
#     W(driver, timeout).until(
#         lambda d: d.execute_script("return document.readyState") == "complete"
#     )


# def clean(txt: str) -> str:
#     """remove \n, \t, múltiplos espaços, trim."""
#     return re.sub(r"\s+", " ", txt or "").strip()


# def build_list_url(q: Optional[str]) -> str:
#     p = {"pagina": 1, "tamanhoPagina": 10, "beneficiarioProgramaSocial": "true"}
#     if q:
#         p["termo"] = q
#     return f"{LIST_ENDPOINT}?{urlencode(p, quote_via=quote_plus)}"


# def save_evidence(driver: webdriver.Chrome, prefix: str):
#     uid = uuid.uuid4().hex[:8]
#     Path(f"error-{prefix}-{uid}.html").write_text(driver.page_source, encoding="utf-8")
#     driver.save_screenshot(f"error-{prefix}-{uid}.png")
#     logger.error("Evidência salva (%s)", uid)


# # ───────────── scraping – pessoas ─────────────
# def wait_for_results(driver: webdriver.Chrome, timeout: int = 30) -> List[str]:
#     wait_dom(driver)
#     end = time.time() + timeout
#     while time.time() < end:
#         links = driver.find_elements(By.CSS_SELECTOR, "#resultados a.link-busca-nome")
#         if links:
#             return [
#                 a.get_attribute("href") or "" for a in links if a.get_attribute("href")
#             ]
#         time.sleep(1)
#     # fallback – regex
#     return [BASE + h for h in anchor_rx.findall(driver.page_source)]


# def search_people(driver: webdriver.Chrome, query: Optional[str]) -> List[str]:
#     url = build_list_url(query)
#     logger.info("Abrindo lista: %s", url)
#     driver.get(url)
#     links = wait_for_results(driver)
#     if not links:
#         save_evidence(driver, "list")
#         raise RuntimeError("Nenhum resultado encontrado.")
#     uniq = list(dict.fromkeys(links))  # dedup preservando ordem
#     return uniq[:10]


# def get_text(driver: webdriver.Chrome, label: str) -> str:
#     xp = f"//strong[normalize-space()='{label}']/following-sibling::span"
#     try:
#         return driver.find_element(By.XPATH, xp).text.strip()
#     except NoSuchElementException:
#         return ""


# # ───────────── scraping – benefícios ─────────────
# def parse_benefit(driver: webdriver.Chrome, url: str) -> List[Dict]:
#     """
#     Retorna TODAS as parcelas do benefício, percorrendo a paginação
#     quando existir.
#     """
#     driver.get(url)
#     wait_dom(driver)

#     # --- identifica o segmento pelo próprio URL ------------------------
#     m = re.search(r"/beneficios/([^/]+)/", url)
#     segmento: str = m.group(1) if m else ""

#     # espera a tabela renderizar
#     W(driver, 30).until(
#         EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
#     )

#     parcelas: List[Dict] = []
#     ja_vistas = 0

#     while True:
#         # linhas ainda não processadas
#         rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")[ja_vistas:]

#         for tr in rows:
#             tds = tr.find_elements(By.TAG_NAME, "td")

#             # ------------------ mapeia colunas conforme o benefício ------------------
#             if segmento == "auxilio-brasil" and len(tds) >= 5:
#                 parcelas.append(
#                     {
#                         "mes_folha": clean(tds[0].text),
#                         "mes_ref": clean(tds[1].text),
#                         "uf": clean(tds[2].text),
#                         "municipio": clean(tds[3].text),
#                         "valor": clean(tds[4].text),
#                     }
#                 )

#             elif segmento == "auxilio-emergencial" and len(tds) >= 7:
#                 parcelas.append(
#                     {
#                         "mes_disponibilizacao": clean(tds[0].text),
#                         "parcela": clean(tds[1].text),
#                         "uf": clean(tds[2].text),
#                         "municipio": clean(tds[3].text),
#                         "enquadramento": clean(tds[4].text),
#                         "valor": clean(tds[5].text),
#                         "observacao": clean(tds[6].text),
#                     }
#                 )

#             elif segmento == "bolsa-familia" and len(tds) >= 6:
#                 parcelas.append(
#                     {
#                         "mes_folha": clean(tds[0].text),
#                         "mes_ref": clean(tds[1].text),
#                         "uf": clean(tds[2].text),
#                         "municipio": clean(tds[3].text),
#                         "qtd_dependentes": clean(tds[4].text),
#                         "valor": clean(tds[5].text),
#                     }
#                 )

#             elif segmento == "novo-bolsa-familia" and len(tds) >= 5:
#                 parcelas.append(
#                     {
#                         "mes_folha": clean(tds[0].text),
#                         "mes_ref": clean(tds[1].text),
#                         "uf": clean(tds[2].text),
#                         "municipio": clean(tds[3].text),
#                         "valor": clean(tds[4].text),
#                     }
#                 )

#             elif segmento == "safra" and len(tds) >= 4:
#                 parcelas.append(
#                     {
#                         "mes_folha": clean(tds[0].text),
#                         "uf": clean(tds[1].text),
#                         "municipio": clean(tds[2].text),
#                         "valor": clean(tds[3].text),
#                     }
#                 )

#         ja_vistas += len(rows)

#         # ------------------ paginação (se existir) ------------------
#         try:
#             nxt_li = driver.find_element(By.ID, "tabelaDetalheValoresSacados_next")
#             li_class = nxt_li.get_attribute("class") or ""  # garante str

#             if "disabled" in li_class:
#                 break  # última página já foi processada

#             # botão dentro do <li>
#             nxt_btn = nxt_li.find_element(By.TAG_NAME, "button")
#             driver.execute_script("arguments[0].click()", nxt_btn)
#             html_after = driver.page_source  # string com todo o DOM atual
#             Path("debug_after_click.html").write_text(html_after, encoding="utf-8")

#             # se quiser só ver no console
#             print("========== HTML depois do clique ==========")
#             print(html_after[:15000])
#             # espera aparecer novas linhas ou a paginação desabilitar
#             W(driver, 15).until(
#                 lambda d: (
#                     len(d.find_elements(By.CSS_SELECTOR, "table tbody tr")) > ja_vistas
#                 )
#                 or "disabled"
#                 in (
#                     d.find_element(
#                         By.ID, "tabelaDetalheValoresSacados_next"
#                     ).get_attribute("class")
#                     or ""
#                 )
#             )

#         except NoSuchElementException:
#             # não existe paginação para esta tabela
#             break
#         except TimeoutException:
#             logger.warning("Timeout esperando próxima página em %s", url)
#             break  # evita loop infinito caso algo trave

#     return parcelas


# def open_recebimentos(driver: webdriver.Chrome, timeout: int = 10):
#     """expande o accordion 'Recebimentos de recursos'."""
#     header = driver.find_element(
#         By.CSS_SELECTOR,
#         "button.header[aria-controls='accordion-recebimentos-recursos']",
#     )
#     try:
#         if "active" not in (header.get_attribute("class") or ""):
#             header.click()
#     except ElementClickInterceptedException:
#         # fecha barra de cookies se estiver sobrepondo
#         try:
#             driver.find_element(By.ID, "cookiebar-close").click()
#             header.click()
#         except Exception:
#             pass

#     W(driver, timeout).until(
#         EC.presence_of_element_located(
#             (By.CSS_SELECTOR, "#accordion-recebimentos-recursos div.br-table")
#         )
#     )


# def collect_cards(driver: webdriver.Chrome) -> List[Dict]:
#     """lê todos os 'cards' de benefício listados no accordion."""
#     cards = []
#     selector = "#accordion-recebimentos-recursos div.br-table div.responsive"
#     for box in driver.find_elements(By.CSS_SELECTOR, selector):
#         try:
#             titulo = clean(
#                 box.find_element(By.TAG_NAME, "strong").get_attribute("textContent")
#             )
#             row = box.find_element(By.CSS_SELECTOR, "tbody tr")
#             cols = [
#                 clean(td.get_attribute("textContent"))
#                 for td in row.find_elements(By.TAG_NAME, "td")
#             ]
#             href = row.find_element(By.CSS_SELECTOR, "a.br-button").get_attribute(
#                 "href"
#             )

#             cards.append(
#                 {
#                     "beneficio": titulo,
#                     "nis": cols[1] if len(cols) > 1 else "",
#                     "nome": cols[2] if len(cols) > 2 else "",
#                     "valor_recebido": cols[3] if len(cols) > 3 else "",
#                     "href": href,
#                     "parcelas": [],
#                 }
#             )
#         except Exception as e:
#             logger.warning("Falha lendo card: %s", e)
#     return cards


# # ───────────── scraping – pessoa ─────────────
# def parse_person(driver: webdriver.Chrome, url: str) -> Dict:
#     logger.info("Processando pessoa: %s", url)
#     driver.get(url)
#     wait_dom(driver)

#     person = {
#         "nome": get_text(driver, "Nome"),
#         "cpf": get_text(driver, "CPF"),
#         "localidade": get_text(driver, "Localidade"),
#         "screenshot": driver.get_screenshot_as_base64(),
#         "beneficios": [],
#     }

#     open_recebimentos(driver)
#     cards = collect_cards(driver)

#     # vai entrando & voltando para coletar parcelas
#     ficha_url = driver.current_url
#     for card in cards:
#         try:
#             card["parcelas"] = parse_benefit(driver, card["href"])
#         except Exception as e:
#             logger.error("Falha no benefício %s: %s", card["href"], e)
#             save_evidence(driver, "beneficio")
#         finally:
#             driver.get(ficha_url)
#             wait_dom(driver)
#             open_recebimentos(driver)

#     person["beneficios"] = cards
#     return person


# # ───────────── runner ─────────────
# def run(query: Optional[str], visible: bool = False):
#     d = new_driver(visible)
#     try:
#         pessoas = []
#         for u in search_people(d, query):
#             try:
#                 pessoas.append(parse_person(d, u))
#             except Exception as e:
#                 logger.error("Erro na pessoa %s: %s", u, e)
#                 save_evidence(d, "person")
#         return {"consulta": query or "*primeiros 10*", "pessoas": pessoas}
#     finally:
#         d.quit()


# # ───────────── CLI ─────────────
# def cli():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--query", default="", help="Filtro (Nome, CPF ou NIS)")
#     ap.add_argument("--out", default="resultado.json", help="Arquivo JSON de saída")
#     ap.add_argument("--visible", action="store_true", help="Mostra navegador")
#     ap.add_argument("--debug", action="store_true", help="Logs no console")
#     args = ap.parse_args()

#     global logger
#     logger = setup_logger(args.debug)
#     try:
#         data = run(args.query.strip() or None, visible=args.visible)
#         Path(args.out).write_text(
#             json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
#         )
#         logger.info("✔ Salvo em %s", args.out)
#     except Exception as e:
#         logger.error("Falha: %s", e)
#         traceback.print_exc()
#         sys.exit(1)


# if __name__ == "__main__":
#     cli()

"""RPA Bot – Portal da Transparência  v2.0
────────────────────────────────────────────────────────────────────────
* Obtém parcelas através do endpoint JSON (/…/sacado|recebido/resultado)
  usando a mesma sessão do Selenium  ➜  sem 403.
* Mantém 100 % da lógica anterior para pessoas, benefícios e evidências.
"""

from __future__ import annotations

import argparse, json, logging, re, sys, time, traceback, uuid
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlencode

import requests
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
)
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

# colunas de cada segmento – para o endpoint JSON
COLUNAS = {
    "auxilio-emergencial": "mesDisponibilizacao,numeroParcela,uf,municipio,enquadramento,valor,observacao",
    "auxilio-brasil": "mesFolha,mesReferencia,uf,municipio,valor",
    "bolsa-familia": "mesFolha,mesReferencia,uf,municipio,quantidadeDependentes,valor",
    "novo-bolsa-familia": "mesFolha,mesReferencia,uf,municipio,valor",
    "safra": "mesFolha,uf,municipio,valor",
}

# alguns segmentos usam /recebido/resultado (AE)  - os demais /sacado/resultado
PATH_JSON = {
    "auxilio-emergencial": "recebido/resultado",
}


def make_api_url(
    segmento: str, benef_id: str, pessoa_id: str, page_size: int = 1000, offset: int = 0
) -> str:
    """
    Constrói a URL JSON das parcelas de qualquer benefício.
    * `segmento`  – trecho que aparece no href: auxilio-emergencial, safra …
    * `benef_id`  – número logo depois do segmento no href (ex.: …/safra/**5230367**)
    * `pessoa_id` – id que vem na ficha da pessoa (…/pessoa-fisica/**6027443**-nome)
    """
    base = f"{BASE}/beneficios/{segmento}/recebido/resultado"

    # parâmetro que muda só para Safra
    id_param = "skBeneficiario" if segmento == "safra" else "beneficiario"

    # coluna que será ordenada (muda em Auxílio-Emergencial)
    col_ord = "numeroParcela" if segmento == "auxilio-emergencial" else "mesFolha"

    # colunas que queremos no JSON (já codificadas com urlencode)
    COLS = {
        "safra": "mesFolha%2Cuf%2Cmunicipio%2Cvalor",
        "auxilio-emergencial": "mesDisponibilizacao%2CnumeroParcela%2Cuf%2Cmunicipio%2Cenquadramento%2Cvalor%2Cobservacao",
        "auxilio-brasil": "mesFolha%2CmesReferencia%2Cuf%2Cmunicipio%2Cvalor",
        "novo-bolsa-familia": "mesFolha%2CmesReferencia%2Cuf%2Cmunicipio%2Cvalor",
        "bolsa-familia": "mesFolha%2CmesReferencia%2Cuf%2Cmunicipio%2CquantidadeDependentes%2Cvalor",
    }

    cols = COLS.get(segmento, "mesFolha%2Cvalor")

    params = (
        f"paginacaoSimples=true"
        f"&tamanhoPagina={page_size}"
        f"&offset={offset}"
        f"&direcaoOrdenacao=desc"
        f"&colunaOrdenacao={col_ord}"
        f"&colunasSelecionadas={cols}"
        f"&{id_param}={benef_id}"
        f"&pessoa={pessoa_id}"
    )
    return f"{base}?{params}"


def get_text(driver: webdriver.Chrome, label: str) -> str:
    """
    No box “dados-tabelados”, encontra:
        <strong>label</strong><span>valor</span>
    e devolve o texto do <span>.  Retorna "" se não achar.
    """
    xp = f"//strong[normalize-space()='{label}']/following-sibling::span"
    try:
        return driver.find_element(By.XPATH, xp).text.strip()
    except NoSuchElementException:
        return ""


# ───────────── logger ─────────────
def setup_logger(show_console: bool = False):
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


# ───────────── webdriver ─────────────
def new_driver(visible: bool = False):
    opt = Options()
    if not visible:
        opt.add_argument("--headless=new")
    opt.add_argument("--window-size=1920,1080")
    opt.add_argument("--disable-gpu")
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-blink-features=AutomationControlled")
    opt.add_argument("--lang=pt-BR")
    opt.add_argument(
        "--user-agent="
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    return webdriver.Chrome(options=opt)  # Selenium Manager resolve o driver


# ───────────── helpers ─────────────
def wait_dom(driver: webdriver.Chrome, timeout: int = 20):
    W(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def clean(txt: str) -> str:
    return re.sub(r"\s+", " ", txt or "").strip()


def build_list_url(q: Optional[str]) -> str:
    p = {"pagina": 1, "tamanhoPagina": 10, "beneficiarioProgramaSocial": "true"}
    if q:
        p["termo"] = q
    return f"{LIST_ENDPOINT}?{urlencode(p, quote_via=quote_plus)}"


def save_evidence(driver: webdriver.Chrome, prefix: str):
    uid = uuid.uuid4().hex[:8]
    Path(f"error-{prefix}-{uid}.html").write_text(driver.page_source, encoding="utf-8")
    driver.save_screenshot(f"error-{prefix}-{uid}.png")
    logger.error("Evidência salva (%s)", uid)


# ───────────── JSON endpoint ─────────────
def fetch_parcelas_json(
    driver: webdriver.Chrome,
    segmento: str,
    sk_beneficiario: str,
    pessoa_id: str,
) -> List[Dict]:
    """
    Usa os cookies do Selenium para chamar o endpoint JSON e devolve
    a lista de parcelas já no formato esperado.
    """
    path = (
        PATH_JSON[segmento]
        if segmento in PATH_JSON
        else "recebido/resultado"
        if segmento == "safra"
        else "sacado/resultado"
    )
    url = f"{BASE}/beneficios/{segmento}/{path}"
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
                    mes_disponibilizacao=clean(row["mesDisponibilizacao"]),
                    parcela=clean(row["numeroParcela"]),
                    uf=clean(row["uf"]),
                    municipio=clean(row["municipio"]),
                    enquadramento=clean(row["enquadramento"]),
                    valor=clean(row["valor"]),
                    observacao=clean(row["observacao"]),
                )
            )
        elif segmento == "auxilio-brasil":
            out.append(
                dict(
                    mes_folha=clean(row["mesFolha"]),
                    mes_ref=clean(row["mesReferencia"]),
                    uf=clean(row["uf"]),
                    municipio=clean(row["municipio"]),
                    valor=clean(row["valor"]),
                )
            )
        elif segmento == "bolsa-familia":
            out.append(
                dict(
                    mes_folha=clean(row["mesFolha"]),
                    mes_ref=clean(row["mesReferencia"]),
                    uf=clean(row["uf"]),
                    municipio=clean(row["municipio"]),
                    qtd_dependentes=clean(row["quantidadeDependentes"]),
                    valor=clean(row["valor"]),
                )
            )
        elif segmento == "novo-bolsa-familia":
            out.append(
                dict(
                    mes_folha=clean(row["mesFolha"]),
                    mes_ref=clean(row["mesReferencia"]),
                    uf=clean(row["uf"]),
                    municipio=clean(row["municipio"]),
                    valor=clean(row["valor"]),
                )
            )
        elif segmento == "safra":
            out.append(
                dict(
                    mes_folha=clean(row["mesFolha"]),
                    uf=clean(row["uf"]),
                    municipio=clean(row["municipio"]),
                    valor=clean(row["valor"]),
                )
            )
    return out


# ───────────── scraping – benefícios ─────────────
def parse_benefit(driver: webdriver.Chrome, url: str, pessoa_id: str) -> List[Dict]:
    """
    Primeiro tenta via endpoint JSON; se falhar, cai no raspador de tabela.
    """
    m = re.search(r"/beneficios/([^/]+)/(\d+)", url)
    segmento = m.group(1) if m else ""
    sk_beneficiario = m.group(2) if m else ""

    # ----------- JSON first -------------------------------------------------
    try:
        return fetch_parcelas_json(driver, segmento, sk_beneficiario, pessoa_id)
    except Exception as e:
        logger.warning("JSON falhou em %s (%s) – fazendo fallback de tela", url, e)

    # -------------- fallback: raspa a tabela visível ------------------------
    driver.get(url)
    wait_dom(driver)
    W(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
    )

    parcelas: List[Dict] = []
    for tr in driver.find_elements(By.CSS_SELECTOR, "table tbody tr"):
        tds = tr.find_elements(By.TAG_NAME, "td")
        if segmento == "auxilio-brasil" and len(tds) >= 5:
            parcelas.append(
                dict(
                    mes_folha=clean(tds[0].text),
                    mes_ref=clean(tds[1].text),
                    uf=clean(tds[2].text),
                    municipio=clean(tds[3].text),
                    valor=clean(tds[4].text),
                )
            )
        elif segmento == "auxilio-emergencial" and len(tds) >= 7:
            parcelas.append(
                dict(
                    mes_disponibilizacao=clean(tds[0].text),
                    parcela=clean(tds[1].text),
                    uf=clean(tds[2].text),
                    municipio=clean(tds[3].text),
                    enquadramento=clean(tds[4].text),
                    valor=clean(tds[5].text),
                    observacao=clean(tds[6].text),
                )
            )
        elif segmento == "bolsa-familia" and len(tds) >= 6:
            parcelas.append(
                dict(
                    mes_folha=clean(tds[0].text),
                    mes_ref=clean(tds[1].text),
                    uf=clean(tds[2].text),
                    municipio=clean(tds[3].text),
                    qtd_dependentes=clean(tds[4].text),
                    valor=clean(tds[5].text),
                )
            )
        elif segmento == "novo-bolsa-familia" and len(tds) >= 5:
            parcelas.append(
                dict(
                    mes_folha=clean(tds[0].text),
                    mes_ref=clean(tds[1].text),
                    uf=clean(tds[2].text),
                    municipio=clean(tds[3].text),
                    valor=clean(tds[4].text),
                )
            )
        elif segmento == "safra" and len(tds) >= 4:
            parcelas.append(
                dict(
                    mes_folha=clean(tds[0].text),
                    uf=clean(tds[1].text),
                    municipio=clean(tds[2].text),
                    valor=clean(tds[3].text),
                )
            )
    return parcelas


# ───────────── scraping – accordion & cards (inalterado) ─────────────
def open_recebimentos(driver: webdriver.Chrome, timeout: int = 10):
    header = driver.find_element(
        By.CSS_SELECTOR,
        "button.header[aria-controls='accordion-recebimentos-recursos']",
    )
    try:
        if "active" not in (header.get_attribute("class") or ""):
            header.click()
    except ElementClickInterceptedException:
        try:
            driver.find_element(By.ID, "cookiebar-close").click()
            header.click()
        except Exception:
            pass

    W(driver, timeout).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#accordion-recebimentos-recursos div.br-table")
        )
    )


def collect_cards(driver: webdriver.Chrome) -> List[Dict]:
    cards = []
    selector = "#accordion-recebimentos-recursos div.br-table div.responsive"
    for box in driver.find_elements(By.CSS_SELECTOR, selector):
        try:
            titulo = clean(
                box.find_element(By.TAG_NAME, "strong").get_attribute("textContent")
            )
            row = box.find_element(By.CSS_SELECTOR, "tbody tr")
            cols = [
                clean(td.get_attribute("textContent"))
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
            logger.warning("Falha lendo card: %s", e)
    return cards


# ───────────── scraping – pessoa ─────────────
def parse_person(driver: webdriver.Chrome, url: str) -> Dict:
    logger.info("Processando pessoa: %s", url)
    driver.get(url)
    wait_dom(driver)

    # id numérico da pessoa física na própria URL
    pessoa_match = re.search(r"/pessoa-fisica/(\d+)-", url)
    pessoa_id = pessoa_match.group(1) if pessoa_match else ""

    person = dict(
        nome=get_text(driver, "Nome"),
        cpf=get_text(driver, "CPF"),
        localidade=get_text(driver, "Localidade"),
        screenshot=driver.get_screenshot_as_base64(),
        beneficios=[],
    )

    open_recebimentos(driver)
    cards = collect_cards(driver)

    ficha_url = driver.current_url
    for card in cards:
        try:
            card["parcelas"] = parse_benefit(driver, card["href"], pessoa_id)
        except Exception as e:
            logger.error("Falha no benefício %s: %s", card["href"], e)
            save_evidence(driver, "beneficio")
        finally:
            driver.get(ficha_url)
            wait_dom(driver)
            open_recebimentos(driver)

    person["beneficios"] = cards
    return person


# ───────────── runner ─────────────
def wait_for_results(driver: webdriver.Chrome, timeout: int = 30) -> List[str]:
    wait_dom(driver)
    end = time.time() + timeout
    while time.time() < end:
        links = driver.find_elements(By.CSS_SELECTOR, "#resultados a.link-busca-nome")
        if links:
            return [
                a.get_attribute("href") or "" for a in links if a.get_attribute("href")
            ]
        time.sleep(1)
    return [BASE + h for h in anchor_rx.findall(driver.page_source)]


def search_people(driver: webdriver.Chrome, query: Optional[str]) -> List[str]:
    url = build_list_url(query)
    driver.get(url)
    links = wait_for_results(driver)
    if not links:
        save_evidence(driver, "list")
        raise RuntimeError("Nenhum resultado encontrado.")
    return list(dict.fromkeys(links))[:10]  # dedup


def run(query: Optional[str], visible: bool = False):
    d = new_driver(visible)
    try:
        pessoas = []
        for u in search_people(d, query):
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
