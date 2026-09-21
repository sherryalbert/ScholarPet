"""Fetch the bundled English -> Chinese model.

The Argos/OPUS model is ~82 MB and would dominate this repository's history, so
it is not version controlled.  ``ScholarPet.spec`` still ships
``models/translate-en_zh-1_9`` into the portable build, which means the folder
has to exist before anyone runs ``scripts/build.ps1`` -- and the offline engine
refuses to start without it.  This script is the documented way to get it::

    python scripts/fetch_model.py              # download and extract
    python scripts/fetch_model.py --check      # report only, change nothing
    python scripts/fetch_model.py --archive translate-en_zh-1_9.argosmodel

``--archive`` exists for two real cases: a machine behind a proxy/firewall that
can move the file by other means, and re-installing from an archive someone
already has.  Both paths produce exactly the same tree, because the archive's
only top-level directory is unpacked away.

Only the standard library is used so this keeps working in a bare interpreter,
before ``requirements.txt`` has been installed.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODEL_DIR_NAME = "translate-en_zh-1_9"
DEFAULT_DEST = REPO / "models" / MODEL_DIR_NAME
DEFAULT_URL = (
    "https://data.argosopentech.com/argospm/v1/translate-en_zh-1_9.argosmodel"
)

# The offline engine needs both of these; ``offline.model_path`` checks for the
# same pair, so a tree that passes here is one the app will accept.
REQUIRED = ("model/model.bin", "sentencepiece.model")

_CHUNK = 1 << 20


def _say(message: str) -> None:
    print(message, flush=True)


def _is_ready(dest: Path) -> bool:
    return all((dest / rel).is_file() for rel in REQUIRED)


def _human(count: int) -> str:
    return f"{count / (1 << 20):.1f} MB"


def _download(url: str, target: Path) -> None:
    _say(f"downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ScholarPet-fetch-model"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            step = max(total // 20, _CHUNK) if total else 0
            reported = 0
            with target.open("wb") as handle:
                while True:
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if step and done // step > reported:
                        reported = done // step
                        share = f"{done * 100 // total}%" if total else _human(done)
                        _say(f"  {share}")
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"download failed: {exc}\n"
            f"Retry, or fetch {url} yourself and pass --archive <file>."
        ) from exc
    _say(f"downloaded {_human(target.stat().st_size)}")


def _extract(archive: Path, dest: Path) -> None:
    """Unpack the archive straight into ``dest``, dropping its wrapper folder.

    ``.argosmodel`` files are plain zips laid out as
    ``translate-en_zh-1_9/<payload>``.  Everyone who consumes them wants the
    payload, so the single leading component is stripped -- which also means the
    result is identical no matter what the wrapper happens to be called.
    """
    if not zipfile.is_zipfile(archive):
        raise SystemExit(f"{archive} is not a .argosmodel (zip) archive")
    staging = Path(tempfile.mkdtemp(prefix="scholarpet-model-"))
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            roots = {m.filename.split("/", 1)[0] for m in members if "/" in m.filename}
            wrapper = roots.pop() if len(roots) == 1 else ""
            for member in members:
                relative = member.filename
                if wrapper and relative.startswith(wrapper + "/"):
                    relative = relative[len(wrapper) + 1:]
                relative = relative.strip("/")
                if not relative:
                    continue
                # Zip-slip guard: never let an entry escape the staging tree.
                target = (staging / relative).resolve()
                if staging.resolve() not in target.parents and target != staging.resolve():
                    raise SystemExit(f"refusing unsafe archive entry: {member.filename}")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle, _CHUNK)
        if not _is_ready(staging):
            missing = [rel for rel in REQUIRED if not (staging / rel).is_file()]
            raise SystemExit(f"archive is incomplete, missing: {', '.join(missing)}")
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(dest))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST,
                        help=f"where to unpack (default: {DEFAULT_DEST})")
    parser.add_argument("--archive", type=Path,
                        help="use this .argosmodel file instead of downloading")
    parser.add_argument("--url", default=DEFAULT_URL,
                        help="override the download URL")
    parser.add_argument("--force", action="store_true",
                        help="re-install even if the model is already complete")
    parser.add_argument("--check", action="store_true",
                        help="report whether the model is installed, then stop")
    args = parser.parse_args(argv)

    dest: Path = args.dest
    if _is_ready(dest) and not args.force:
        biggest = dest / REQUIRED[0]
        _say(f"model already installed: {dest} ({_human(biggest.stat().st_size)})")
        return 0
    if args.check:
        _say(f"model NOT installed at {dest}")
        return 1

    archive = args.archive
    if archive is not None:
        archive = archive.expanduser().resolve()
        if not archive.is_file():
            raise SystemExit(f"no such archive: {archive}")
        _say(f"using local archive {archive}")
        _extract(archive, dest)
    else:
        with tempfile.TemporaryDirectory(prefix="scholarpet-download-") as work:
            download = Path(work) / f"{MODEL_DIR_NAME}.argosmodel"
            _download(args.url, download)
            _extract(download, dest)

    total = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
    _say(f"installed to {dest} ({_human(total)})")
    _say("offline English->Chinese translation is ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
