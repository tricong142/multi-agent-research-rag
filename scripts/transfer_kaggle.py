"""Build and verify a Kaggle dataset archive for this workspace.

The archive contains runtime/evaluation files and local model/index artifacts,
but excludes virtual environments, Git metadata, caches and secret files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    "research_rag",
    "train_agent1_retrieval",
    "train_agent2_reader",
    "train_agent3_summarizer",
    "04_factchecker",
    "05_writer",
    "kb_indexing",
    "docs",
    "scripts",
)
ROOT_FILES = (
    "requirements-orchestrator.txt",
    "README.md",
    "NOTICE.txt",
    "THIRD_PARTY_NOTICES.md",
    "THIRD_PARTY_QWEN_3B_LICENSE.txt",
)
REQUIRED = (
    "kb_indexing/data/corpus.jsonl",
    "kb_indexing/indices/bm25_index.pkl",
    "kb_indexing/indices/faiss_arxiv.index",
    "kb_indexing/indices/faiss_doc_ids.json",
    "train_agent2_reader/layoutlmv3_doclaynet_model/model.safetensors",
    "train_agent3_summarizer/checkpoints/generator_qlora/final/adapter_model.safetensors",
    "train_agent3_summarizer/checkpoints/critic_qlora/final/adapter_model.safetensors",
    "04_factchecker/checkpoints/factchecker_merged/model-00001-of-00002.safetensors",
    "04_factchecker/checkpoints/factchecker_merged/model-00002-of-00002.safetensors",
    "05_writer/checkpoints/writer_qlora/adapter_model.safetensors",
)
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "_archive"}
SKIP_SUFFIXES = {".log", ".tmp", ".pyc", ".pem", ".key", ".p12", ".pfx"}
TEXT_SUFFIXES = {".py", ".json", ".jsonl", ".md", ".txt", ".csv", ".yaml", ".yml", ".toml", ".ipynb"}
MANIFEST_NAME = "transfer-manifest.json"


def selected_files() -> list[Path]:
    paths = [ROOT / name for name in ROOT_FILES]
    for name in DIRECTORIES:
        directory = ROOT / name
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        for current, dirs, files in os.walk(directory, followlinks=False):
            current_path = Path(current)
            for item in dirs:
                if (current_path / item).is_symlink():
                    raise ValueError(f"Symlink directory cannot be packaged: {item}")
            dirs[:] = [item for item in dirs if item not in SKIP_DIRS and not item.startswith(".")]
            for item in files:
                path = current_path / item
                if path.is_symlink():
                    raise ValueError(f"Symlink file cannot be packaged: {item}")
                if item.startswith(".") or path.suffix.lower() in SKIP_SUFFIXES:
                    continue
                if item.lower() in {"kaggle.json", "credentials.json", "secrets.json"}:
                    continue
                paths.append(path)
    for path in paths:
        if not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Missing or out-of-workspace file: {path}")
    relative = {path.relative_to(ROOT).as_posix() for path in paths}
    missing = sorted(set(REQUIRED) - relative)
    if missing:
        raise FileNotFoundError(f"Required artifacts are missing: {missing}")
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def digest(stream) -> str:
    sha = hashlib.sha256()
    for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
        sha.update(block)
    return sha.hexdigest()


def build(output: Path) -> None:
    output = output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("Output archive must stay inside the workspace")
    files = selected_files()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Archive already exists: {output}")
    entries = []
    try:
        with zipfile.ZipFile(output, "w", allowZip64=True, strict_timestamps=False) as archive:
            for path in files:
                relative = path.relative_to(ROOT).as_posix()
                with path.open("rb") as source:
                    sha256 = digest(source)
                size = path.stat().st_size
                method = zipfile.ZIP_DEFLATED if path.suffix.lower() in TEXT_SUFFIXES else zipfile.ZIP_STORED
                archive.write(path, relative, compress_type=method, compresslevel=6 if method == zipfile.ZIP_DEFLATED else None)
                entries.append({"path": relative, "size": size, "sha256": sha256})
                if path.suffix.lower() == ".safetensors" or relative in REQUIRED:
                    print(f"packed {relative} ({size / 1024**2:.1f} MiB)", flush=True)
            manifest = {"format_version": 1, "files": entries, "required": list(REQUIRED)}
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(f"created {output} with {len(entries)} files ({output.stat().st_size / 1024**3:.2f} GiB)")
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def _manifest_from_zip(archive: zipfile.ZipFile) -> dict:
    return json.loads(archive.read(MANIFEST_NAME))


def verify_zip(path: Path, full: bool) -> None:
    with zipfile.ZipFile(path) as archive:
        manifest = _manifest_from_zip(archive)
        names = set(archive.namelist())
        expected = {entry["path"] for entry in manifest["files"]}
        if names != expected | {MANIFEST_NAME} or not set(REQUIRED) <= expected:
            raise ValueError("Archive files do not match manifest or required artifacts")
        for entry in manifest["files"]:
            info = archive.getinfo(entry["path"])
            if info.file_size != entry["size"]:
                raise ValueError(f"Size mismatch: {entry['path']}")
            if full:
                with archive.open(info) as source:
                    if digest(source) != entry["sha256"]:
                        raise ValueError(f"SHA-256 mismatch: {entry['path']}")
    print(f"ZIP verified: {len(expected)} files; hashes_checked={full}")


def verify_dir(root: Path, full: bool) -> None:
    root = root.resolve()
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    expected = {entry["path"] for entry in manifest["files"]}
    if not set(REQUIRED) <= expected:
        raise ValueError("Manifest is missing required artifacts")
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.is_file() or not path.resolve().is_relative_to(root) or path.stat().st_size != entry["size"]:
            raise ValueError(f"Missing or wrong-size file: {entry['path']}")
        if full:
            with path.open("rb") as source:
                if digest(source) != entry["sha256"]:
                    raise ValueError(f"SHA-256 mismatch: {entry['path']}")
    print(f"Directory verified: {len(expected)} files; hashes_checked={full}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build_command = sub.add_parser("build")
    build_command.add_argument("--output", type=Path, default=ROOT / "kaggle_transfer/research-rag-kaggle-v3.zip")
    zip_command = sub.add_parser("verify-zip")
    zip_command.add_argument("--archive", type=Path, required=True)
    dir_command = sub.add_parser("verify-dir")
    dir_command.add_argument("--root", type=Path, required=True)
    for command in (zip_command, dir_command):
        command.add_argument("--full", action="store_true", help="Read every file and compare SHA-256 hashes")
    args = parser.parse_args()
    if args.command == "build":
        build(args.output)
    elif args.command == "verify-zip":
        verify_zip(args.archive, args.full)
    else:
        verify_dir(args.root, args.full)


if __name__ == "__main__":
    main()
