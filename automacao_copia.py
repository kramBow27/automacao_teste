import argparse, json, logging, traceback, sys, re, time, uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urlencode
from typing import Dict, List, Optional
from selenium import webdriver
import requests
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
)
from selenium.webdriver.support.ui import WebDriverWait as W
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

##CAMINHO RAIZ DO PORTAL
BASE = "https://portaldatransparencia.gov.br"
LIST_ENDPOINT = f"{BASE}/pessoa-fisica/busca/lista"
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

## pré compila um padrão de busca em URLs em tags a que além de conter busca/pessoa-fisica/ também tem a classe link-busca-nome
anchor_rx = re.compile(
    r'href="(/busca/pessoa-fisica/[^"]+)"[^>]*class="link-busca-nome"'
)


def new_driver(visible: bool = False):
    opt = Options()
    if not visible:
        ## se o parametro for falso, então o navegador não é exibido
        opt.add_argument("--headless=new")
    ## define um parametro pro tamanho de tela, importante para obter as screenshots
    opt.add_argument("--window-size=1920,1080")
    ## desativa aceleração por gpu, pode dificultar execução do parametro headless em alguns ambientes
    opt.add_argument("--disable-gpu")
    ## desabilita o sandbox de segurança do chrome, necessário quando usuário não tem permissões necessárias
    opt.add_argument("--no-sandbox")
    ## remove sinalizadores que possam permitir que as paginas detectem o driver automatizado
    opt.add_argument("--disable-blink-features=AutomationControlled")
    ## sobrescreve o user agent padrão do chrome, evita que o navegador detecte que é um bot
    opt.add_argument(
        "--user-agent="
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120 Safari/537.36"
    )
    ## retorna uma instancia do webdriver do chrome, poderia ser passado um parametro para a função para definir o navegador de escolha, mas por convenção foi utilizado o retorno do chrome
    return webdriver.Chrome(options=opt)


def espera_dom(driver: webdriver.Chrome, timeout: int = 20):
    ## Espera o dom estar carregado, com html e js prontos pro consumo do driver, com um timeout de 20 segundos
    W(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def espera_resultados(driver: webdriver.Chrome, timeout: int = 30) -> List[str]:
    ##função para esperar o carregamento do DOM
    espera_dom(driver)
    ## Calcula o momento atual somado ao timeout, ou seja, o "horário" que o timeout expira
    fim = time.time() + timeout
    ## enquanto o agora for antes do fim,  busca os links dos beneficiários na lista da pagina
    while time.time() < fim:
        ## busca, dentro da classe resultados, os <a> que tem classe link-busca-nome ,e adiciona a lista links
        links = driver.find_elements(By.CSS_SELECTOR, "#resultados a.link-busca-nome")
        if links:
            ## se houver links, retorna o href de cada um deles em uma lista
            return [
                a.get_attribute("href") or "" for a in links if a.get_attribute("href")
            ]
        time.sleep(1)
    ## se o loop acabe sem encontrar nada pelo CSS, usa regex para extrair os links diretamente do html bruto, e em seguida monta as urls completas somando eles a base
    return [BASE + h for h in anchor_rx.findall(driver.page_source)]


def url_lista_beneficiarios(query: Optional[str]):
    ## de maneira geral, essa função adiciona os parametros de busca na url principal
    params = {"pagina": 1, "tamanhoPagina": 10, "beneficiarioProgramaSocial": "true"}
    if query:
        params["termo"] = query
    return f"{LIST_ENDPOINT}?{urlencode(params, quote_via=quote_plus)}"


def salva_evidencia(driver: webdriver.Chrome, prefixo: str):
    uid = uuid.uuid4().hex[:8]
    Path(f"{prefixo}_{uid}.html").write_text(driver.page_source, encoding="utf-8")
    driver.save_screenshot(f"{prefixo}_{uid}.png")
    logger.info("Evidência salva: %s", f"{prefixo}_{uid}")


def busca_beneficiarios(driver: webdriver.Chrome, query: Optional[str]):
    ## gera a url que vai ser usada para obter os 10 beneficiários
    url = url_lista_beneficiarios(query)
    ## instrui o webdriver para abrir a url gerada, espera o carregamento inicial do DOM
    driver.get(url)
    ## pega os links dos beneficarios, espera o carregamento do DOM e os links
    links = espera_resultados(driver)

    if not links:
        ## salva evidencia de erro
        salva_evidencia(driver, "erro_lista")
        raise RuntimeError("Nenhum beneficiário encontrado")
    ## salva evidencia de sucesso e retorna a lista de links como dicionario, com limite de 10 itens
    salva_evidencia(driver, "sucesso_lista")
    return list(dict.fromkeys(links))[:10]


def get_texto(driver: webdriver.Chrome, label: str) -> str:
    xp = f"//strong[normalize-space()='{label}']/following-sibling::span"
    try:
        return driver.find_element(By.XPATH, xp).text.strip()
    except NoSuchElementException:
        return ""


def abrir_beneficios(driver: webdriver.Chrome, timeout: int = 10):
    ## Procura o header do acoordion de recebimentos
    header = driver.find_element(
        By.CSS_SELECTOR,
        "button.header[aria-controls='accordion-recebimentos-recursos']",
    )
    try:
        ## Se o header não tiver a classe active, então clica nele para abrir o accordion
        if "active" not in (header.get_attribute("class") or ""):
            header.click()
    except ElementClickInterceptedException:
        try:
            ## Caso haja a exceção de clique interceptado, tenta fechar o cookiebar, e clica novamente no header
            driver.find_element(By.ID, "cookiebar_close").click()
            header.click()
        except Exception:
            pass
    ## espera até que a tabela do acoordion dde beneficios tenha sido aberta
    W(driver, timeout).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#accordion-recebimentos-recursos div.br-table")
        )
    )


def higienizar(txt: str) -> str:
    return re.sub(r"\s+", " ", txt or "").strip()


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
    ## Coleta os cards de beneficios, que são os elementos filhos do accordion de recebimentos
    cards = []
    ## Seleciona o accordion de recebimentos, e para cada elemento filho, coleta os dados do card, buscando pela classe responsive dentro da div br-table
    selector = "#accordion-recebimentos-recursos div.br-table div.responsive"
    for box in driver.find_elements(By.CSS_SELECTOR, selector):
        try:
            ## para cada item dentro do seletor, pega o elemento strong que tem o nome do beneficio, e o texto dos filhos da tag tr dentro do tbody, e o href do link de detalhes do beneficio
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
            ## adiciona o card a lista de cards, com os dados coletados, e o href do link de detalhes do beneficio
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
    ## Obtem o nome do beneficio e id do beneficiario da url, se não encontrar, retorna vazio
    m = re.search(r"/beneficios/([^/]+)/(\d+)", url)
    segmento = m.group(1) if m else ""
    sk_beneficiario = m.group(2) if m else ""

    try:
        return fetch_parcelas_json(driver, segmento, sk_beneficiario, beneficiario_id)
    except Exception as e:
        logger.warning("Erro ao coletar parcelas: %s", e)

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
    logger.info("Processando beneficiario %s", url)
    ## abre a url do beneficiario, espera o carregamento do DOM
    driver.get(url)
    espera_dom(driver)
    ## pega o id do beneficiario da url, se não encontrar, retorna vazio
    beneficiario_match = re.search(r"/pessoa-fisica/(\d+)-", url)
    beneficiario_id = beneficiario_match.group(1) if beneficiario_match else ""
    ## cria o objeto do beneficiario, com os dados obtidos do DOM, e adiciona o screenshot em base64
    beneficiario = dict(
        nome=get_texto(driver, "Nome"),
        cpf=get_texto(driver, "CPF"),
        localidade=get_texto(driver, "Localidade"),
        screenshot=driver.get_screenshot_as_base64(),
        beneficios=[],
    )
    ## Abre a aba de recebimentos, espera o carregamento do dom
    abrir_beneficios(driver)
    cards = coletar_cards(driver)

    ficha_url = driver.current_url
    for card in cards:
        try:
            card["parcelas"] = mapea_beneficio(driver, card["href"], beneficiario_id)
        except Exception as e:
            logger.error("Erro no beneficio %s: %s", card["herf"], e)
            salva_evidencia(driver, "beneficio")
        finally:
            driver.get(ficha_url)
            espera_dom(driver)
            abrir_beneficios(driver)
    beneficiario["beneficios"] = cards
    return beneficiario


def run(query: Optional[str], visible: bool = False):
    ##cria web driver do selenium responsável por controlar o navegador, recebe parametro para exibir ou não o navegador
    driver = new_driver(visible)
    try:
        beneficiarios = []
        ## para cada item retornado na busca de beneficiarios, adiciona o objeto mapeado(com as propriedades atribuidas) a lista, se der erro, salva o erro como imagem
        for b in busca_beneficiarios(driver, query):
            try:
                beneficiarios.append(mapea_beneficiario(driver, b))
            except Exception as e:
                logger.error("Erro no beneficiario %s: %s", b, e)
                salva_evidencia(driver, "beneficiario")
        return {"consulta": query, "beneficiarios": beneficiarios}
    finally:
        driver.quit()


def setup_logger(show_console: bool = False):
    ## Define formato de exibição do log
    fmt = "%(asctime)s - %(levelname)s - %(message)s"
    ## Obtem ou cria o logger com nome rpa
    lg = logging.getLogger("rpa")
    ## Define o nivel de log como debug, caputra tudo
    lg.setLevel(logging.DEBUG)
    ## Evita duplicação de handlers
    lg.handlers.clear()
    ## Cria um file handler que salva os logs no arquivo rpa.log
    fh = logging.FileHandler("rpa.log", encoding="utf-8")
    ## associa o formater ao arquivo de log, com
    fh.setFormatter(logging.Formatter(fmt))
    ## associa o gerenciador de arquivo ao logger
    lg.addHandler(fh)
    ## se o parametro show console tiver sido passado, então ele vai exibir os logs no terminal
    if show_console:
        ## avisa para os logs serem exibidos no console
        ch = logging.StreamHandler(sys.stdout)
        ## adiciona formatação ao console tambem
        ch.setFormatter(logging.Formatter(fmt))
        ## adiciona mais um handler para gerenciar a exibição no console
        lg.addHandler(ch)
    ## retorna o logger configurado
    return lg


def cli():
    ap = argparse.ArgumentParser(description="Obtenção de dados de beneficiários")
    ap.add_argument("--query", default="", help="Filtro de busca (Nome, CPF ou NIS)")
    ap.add_argument("--out", default="beneficiarios.json", help="Arquivo Json de Saída")
    ap.add_argument("--visible", action="store_true", help="Exibir navegador")
    ap.add_argument("--debug", action="store_true", help="Exibe logs")
    args = ap.parse_args()

    global logger
    logger = setup_logger(args.debug)
    try:
        data = run(args.query.strip() or None, args.visible)
        Path(args.out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("Salvo em %s", args.out)
    except Exception as e:
        logger.error("Falha ao executar: %s", e)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    cli()
