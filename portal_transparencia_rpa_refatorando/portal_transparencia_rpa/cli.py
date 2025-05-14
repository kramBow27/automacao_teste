import argparse, json, logging, sys, traceback
from pathlib import Path
from typing import List

from .utils import (
    get_run_dir,
)


from .pipeline import run


def setup_logger(debug: bool = False, logfile: Path | None = None) -> logging.Logger:
    fmt = "%(asctime)s - %(levelname)s - %(message)s"

    # ⬇️ declare o tipo como Handler genérico
    handlers: List[logging.Handler] = [
        logging.FileHandler(logfile or "rpa.log", "w", "utf-8"),
    ]
    if debug:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=fmt,
        handlers=handlers,
    )
    return logging.getLogger("rpa")


def main():
    ap = argparse.ArgumentParser(description="Scraper Portal da Transparência")
    ap.add_argument("--query", help="Nome, CPF ou NIS")
    ap.add_argument("--out", default="beneficiarios.json")
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    run_dir = get_run_dir()
    setup_logger(args.debug, logfile=run_dir / "rpa.log")
    try:
        json_out = run_dir / "json" / args.out

        data = run(args.query, args.visible, base_dir=run_dir)
        json_out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Salvo em {json_out}")
    except Exception as e:
        logging.getLogger("rpa").exception("Falha geral")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
