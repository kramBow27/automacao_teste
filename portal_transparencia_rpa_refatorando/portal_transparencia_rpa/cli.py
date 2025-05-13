import argparse, json, logging, sys, traceback
from pathlib import Path
from .pipeline import run


def setup_logger(debug=False):
    fmt = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler("rpa.log", "w", "utf-8"),
            logging.StreamHandler(sys.stdout) if debug else logging.NullHandler(),
        ],
    )
    return logging.getLogger("rpa")


def main():
    ap = argparse.ArgumentParser(description="Scraper Portal da Transparência")
    ap.add_argument("--query", help="Nome, CPF ou NIS")
    ap.add_argument("--out", default="beneficiarios.json")
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    setup_logger(args.debug)
    try:
        data = run(args.query, args.visible)
        Path(args.out).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Salvo em {args.out}")
    except Exception as e:
        logging.getLogger("rpa").exception("Falha geral")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
