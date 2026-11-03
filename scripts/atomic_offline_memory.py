"""Keep offline hash verification byte-identical with smaller read buffers."""
import hashlib
from pathlib import Path
import sys


def file_sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            result.update(chunk)
    return result.hexdigest()


def use_streaming_hashes(runner):
    original = runner.sha256
    for module in list(sys.modules.values()):
        if getattr(module, "__dict__", {}).get("sha256") is original:
            module.sha256 = file_sha256
