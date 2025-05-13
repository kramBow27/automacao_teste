from pathlib import Path
from dotenv import load_dotenv
import os, re

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# URLs
BASE_URL = os.getenv("BASE_URL", "https://portaldatransparencia.gov.br")
LIST_ENDPOINT = f"{BASE_URL}/pessoa-fisica/busca/lista"

# Colunas por benefício
COLUNAS = {
    "auxilio-emergencial": "mesDisponibilizacao,numeroParcela,uf,municipio,enquadramento,valor,observacao",
    "auxilio-brasil": "mesFolha,mesReferencia,uf,municipio,valor",
    "bolsa-familia": "mesFolha,mesReferencia,uf,municipio,quantidadeDependentes,valor",
    "novo-bolsa-familia": "mesFolha,mesReferencia,uf,municipio,valor",
    "safra": "mesFolha,uf,municipio,valor",
}

# Endpoints JSON que fogem ao padrão
PATH_JSON = {"auxilio-emergencial": "recebido/resultado"}

# Regex pré-compiladas
ANCHOR_RX = re.compile(
    r'href="(/busca/pessoa-fisica/[^"]+)"[^>]*class="link-busca-nome"'
)
