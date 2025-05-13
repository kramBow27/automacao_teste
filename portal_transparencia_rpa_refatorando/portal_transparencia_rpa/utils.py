import re, time, logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as W
from selenium.webdriver.support import expected_conditions as EC

log = logging.getLogger("rpa")


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
