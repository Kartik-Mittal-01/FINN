"""Load (or reset) the labelled SYNTHETIC demo dataset: 18 companies, prices, filings, financials and sample PDFs.

    python -m scripts.seed_demo            # from the backend/ folder
    python -m scripts.seed_demo --no-docs  # skip generating the sample PDFs (faster)

Everything it creates is flagged is_demo and shown as SAMPLE DATA in the UI. It never touches live-mode rows.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db  # noqa: E402
from app.services.demo_seed import seed_demo  # noqa: E402
from app.services.state import set_setting  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-docs", action="store_true", help="do not generate sample annual-report / concall PDFs")
    a = ap.parse_args()
    init_db()
    with SessionLocal() as db:
        out = seed_demo(db, with_documents=not a.no_docs)
        set_setting(db, "data_mode", "demo")
    print("Demo dataset loaded:", out)


if __name__ == "__main__":
    main()
