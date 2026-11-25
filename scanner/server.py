def _us_all() -> list[str]:
    data = Path(__file__).resolve().parent / "data"
    blobs = []
    single = data / "us.txt"
    if single.exists():
        blobs.append(single.read_text())
    parts = data / "parts"
    if parts.is_dir():
        for path in sorted(parts.glob("*.txt")):
            blobs.append(path.read_text())
    rows = []
    for blob in blobs:
        rows.extend(blob.splitlines())
    if not rows:
        return list(US)
    out = []
    seen = set()
    for row in rows:
        sym = row.strip().upper()
        if sym and not sym.startswith("#") and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out or list(US)
