"""Download UCI Online Retail II and convert its two Excel sheets into one CSV Spark can read."""
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from src import config  # noqa: E402


def main() -> None:
    if config.RAW_CSV.exists():
        print(f"CSV already present: {config.RAW_CSV}")
        return
    if not config.RAW_XLSX.exists():
        if not config.RAW_ZIP.exists():
            print(f"Downloading {config.DATASET_URL} ...")
            urllib.request.urlretrieve(config.DATASET_URL, config.RAW_ZIP)
        with zipfile.ZipFile(config.RAW_ZIP) as zf:
            member = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
            config.RAW_XLSX.write_bytes(zf.read(member))

    print("Reading both sheets (this takes a minute) ...")
    sheets = pd.read_excel(config.RAW_XLSX, sheet_name=None, dtype={"Invoice": str, "StockCode": str})
    frames = []
    for name, frame in sheets.items():
        print(f"  {name}: {len(frame):,} rows")
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    df.to_csv(config.RAW_CSV, index=False)
    print(f"Wrote {len(df):,} rows -> {config.RAW_CSV}")


if __name__ == "__main__":
    main()
