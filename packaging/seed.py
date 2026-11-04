"""Refresh the painter lists and their paintings that ship with the app
(src/museum_wallpapers/data/fame-<sitelinks>.json.gz), so a first start
needs no Wikidata query. Run before a release and commit the result:

    .venv/bin/python packaging/seed.py

Takes about a minute (two SPARQL queries per fame level)."""

import gzip
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
# A throwaway home: the queries must not be answered from this Mac's cache.
os.environ["MUSEUM_WALLPAPERS_PLATFORM"] = "dev"
os.environ["MUSEUM_WALLPAPERS_HOME"] = tempfile.mkdtemp(prefix="museum-wallpapers-seed-")

from museum_wallpapers import core  # noqa: E402

OUT = ROOT / "src" / "museum_wallpapers" / "data"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, level in core.FAME.items():
        if not level:
            continue  # "any" picks random Commons scans, no list
        started = time.time()
        ids = core._query_painters(level)
        filters = dict(core.normalize_filters({}), fameArtists=ids)
        items = core._query_pool(core.CACHE / "pools" / "seed.json", filters)
        if not items:
            raise SystemExit(f"{name}: Wikidata returned no paintings")
        data = json.dumps({"at": time.time(), "ids": ids, "items": items},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        path = OUT / f"fame-{level}.json.gz"
        # mtime=0: the same data gives the same file.
        with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as f:
            f.write(data)
        print(f"{name}: {len(ids)} painters, {len(items)} paintings, {path.stat().st_size // 1024} KB "
              f"({time.time() - started:.0f} s) -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
