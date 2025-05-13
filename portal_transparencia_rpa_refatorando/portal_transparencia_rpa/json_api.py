import requests, logging
from .constants import BASE_URL, COLUNAS, PATH_JSON

log = logging.getLogger("rpa")


def fetch_parcelas(segmento: str, driver, sk_beneficiario: str, pessoa_id: str):
    path = PATH_JSON.get(
        segmento, "sacado/resultado" if segmento != "safra" else "recebido/resultado"
    )
    url = f"{BASE_URL}/beneficios/{segmento}/{path}"

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
    for c in driver.get_cookies():
        sess.cookies.set(c["name"], c["value"])

    resp = sess.get(
        url, params=params, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
