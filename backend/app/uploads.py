"""Parse and validate uploaded CSV / JSON files into raw sensor frames.

Every problem is raised as InputError -> 400 Bad Request (413 when too large),
with row-level details so the client can fix the file.
"""
import io
import json
from pathlib import Path

import pandas as pd
from pydantic import TypeAdapter, ValidationError

from . import config
from .errors import InputError, pydantic_details
from .schemas import SensorReading
from features import RAW_COLUMNS

MAX_DETAILS = 20
READINGS = TypeAdapter(list[SensorReading])
ALLOWED = {".csv": "csv", ".json": "json"}


def parse_upload(filename: str | None, content: bytes, expect: str | None = None) -> pd.DataFrame:
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise InputError(f"File exceeds {config.MAX_UPLOAD_BYTES // 1_000_000} MB limit", status_code=413)
    ext = Path(filename or "").suffix.lower()
    kind = ALLOWED.get(ext)
    if kind is None or (expect and kind != expect):
        allowed = f".{expect}" if expect else ".csv or .json"
        raise InputError(f"Unsupported file type '{ext or 'none'}': upload a {allowed} file",
                         [{"field": "file", "message": f"expected {allowed}"}])
    if not content.strip():
        raise InputError("Uploaded file is empty", [{"field": "file", "message": "empty file"}])
    if b"\x00" in content[:4096]:
        raise InputError("File is binary, not a text CSV/JSON file", [{"field": "file", "message": "binary content"}])
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("File must be UTF-8 encoded text", [{"field": "file", "message": "not UTF-8"}])

    df = _parse_json(text) if kind == "json" else _parse_csv(text)
    if len(df) > config.MAX_BATCH_ROWS:
        raise InputError(f"File has {len(df):,} rows; limit is {config.MAX_BATCH_ROWS:,}", status_code=413)
    return df


def _parse_json(text: str) -> pd.DataFrame:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise InputError(f"Malformed JSON: {e.msg} (line {e.lineno}, column {e.colno})",
                         [{"field": "file", "message": e.msg}])
    if isinstance(payload, dict):
        payload = payload.get("readings", [payload] if "Type" in payload or "type" in payload else None)
    if not isinstance(payload, list):
        raise InputError("JSON must be a list of readings or an object with a 'readings' list",
                         [{"field": "readings", "message": "expected a list"}])
    if not payload:
        raise InputError("JSON contains no readings", [{"field": "readings", "message": "empty list"}])
    if len(payload) > config.MAX_BATCH_ROWS:
        raise InputError(f"File has {len(payload):,} rows; limit is {config.MAX_BATCH_ROWS:,}", status_code=413)
    try:
        readings = READINGS.validate_python(payload)
    except ValidationError as e:
        details = pydantic_details(e.errors(), row_offset=1)
        raise InputError(f"{len(details)} invalid value(s) in JSON readings", details[:MAX_DETAILS])
    return pd.DataFrame([r.to_raw() for r in readings])


def _canonical(col: str) -> str | None:
    canon = {c.lower().replace(" ", "_"): c for c in RAW_COLUMNS}
    return canon.get(col.split("[")[0].strip().lower().replace(" ", "_"))


def _parse_csv(text: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, skipinitialspace=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise InputError(f"Malformed CSV: {str(e).strip()}", [{"field": "file", "message": "cannot parse CSV"}])
    df = df.rename(columns={c: _canonical(c) for c in df.columns if _canonical(c)})
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise InputError(f"Missing required column(s): {', '.join(missing)}",
                         [{"field": c, "message": "column missing"} for c in missing])
    df = df[RAW_COLUMNS].copy()
    if df.empty:
        raise InputError("CSV has a header but no data rows", [{"field": "file", "message": "no rows"}])

    details = []
    df["Type"] = df["Type"].fillna("").str.strip().str.upper()
    for i in df.index[~df["Type"].isin(["L", "M", "H"])]:
        details.append({"field": "Type", "row": int(i) + 1, "message": f"must be L, M or H (got '{df.at[i, 'Type']}')"})
    for c in RAW_COLUMNS[1:]:
        num = pd.to_numeric(df[c].str.strip(), errors="coerce")
        for i in df.index[num.isna()]:
            details.append({"field": c, "row": int(i) + 1, "message": f"not a number: '{df.at[i, c]}'"})
        df[c] = num
    if details:
        details.sort(key=lambda d: d["row"])
        raise InputError(f"{len(details)} invalid value(s) in CSV", details[:MAX_DETAILS])

    # Range / physics checks reuse the Pydantic schema (one source of truth)
    try:
        READINGS.validate_python(df.astype({c: float for c in RAW_COLUMNS[1:]}).to_dict("records"))
    except ValidationError as e:
        details = pydantic_details(e.errors(), row_offset=1)
        raise InputError(f"{len(details)} out-of-range value(s) in CSV", details[:MAX_DETAILS])
    return df
