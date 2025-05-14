import re, time, logging
from selenium.webdriver.common.by import By
from pathlib import Path
from datetime import datetime
from selenium.webdriver.support.ui import WebDriverWait as W
from selenium.webdriver.support import expected_conditions as EC

log = logging.getLogger("rpa")


def get_run_dir() -> Path:
    ts = datetime.now().strftime("test_%Y-%m-%d_%H-%M-%S")
    base = Path("test_data") / ts
    # subpastas
    for sub in ("json", "html", "png"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def higienizar(txt: str) -> str:
    return re.sub(r"\s+", " ", txt or "").strip()


def espera_dom(driver, timeout: int = 20):
    W(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def espera_css(driver, selector: str, timeout: int = 30):
    espera_dom(driver, timeout)
    W(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )
