"""Read-only checks before loading the five local models."""

from __future__ import annotations

import argparse
import importlib
import json
import time
from pathlib import Path
from typing import Any

from .local import ROOT
from .retrieval import EMBEDDING_MODEL, EMBEDDING_REVISION


def _weight_files(model: str | Path, *, revision: str | None = None) -> dict[str, Any]:
    """Check that every shard named in the model index is present locally."""
    from huggingface_hub import try_to_load_from_cache

    def locate(name: str) -> Path | None:
        if isinstance(model, Path):
            candidate = model / name
            return candidate if candidate.is_file() else None
        cached = try_to_load_from_cache(model, name, revision=revision)
        return Path(cached) if isinstance(cached, str) and Path(cached).is_file() else None

    index = locate("model.safetensors.index.json")
    if index:
        mapping = json.loads(index.read_text(encoding="utf-8"))["weight_map"]
        names = sorted(set(mapping.values()))
    else:
        names = ["model.safetensors"]
    found = [locate(name) for name in names]
    return {"weights_complete": all(found), "shards_found": sum(path is not None for path in found),
            "shards_expected": len(names), "weight_bytes_found": sum(path.stat().st_size for path in found if path)}


def inspect_models() -> dict[str, Any]:
    checkpoints = {
        "summarizer_generator": ROOT / "train_agent3_summarizer/checkpoints/generator_qlora/final",
        "summarizer_critic": ROOT / "train_agent3_summarizer/checkpoints/critic_qlora/final",
        "factchecker": ROOT / "04_factchecker/checkpoints/factchecker_merged",
        "writer": ROOT / "05_writer/checkpoints/writer_qlora",
    }
    models: dict[str, Any] = {}
    for name, directory in checkpoints.items():
        if name == "factchecker":
            adapter_config = ROOT / "04_factchecker/checkpoints/factchecker_qlora/final/adapter_config.json"
            training_base = json.loads(adapter_config.read_text(encoding="utf-8"))["base_model_name_or_path"]
            configured_base = importlib.import_module("04_factchecker.config").BASE_MODEL_NAME
            models[name] = {"checkpoint": _weight_files(directory), "training_base_model": training_base,
                            "configured_base_model": configured_base,
                            "base_matches_adapter": configured_base == training_base,
                            "loaded_from": "merged_local"}
            continue
        config_path = directory / "adapter_config.json"
        if not config_path.is_file():
            models[name] = {"adapter_present": False}
            continue
        config = json.loads(config_path.read_text(encoding="utf-8"))
        base_name = config["base_model_name_or_path"]
        adapter = directory / "adapter_model.safetensors"
        models[name] = {
            "adapter_present": adapter.is_file(), "adapter_bytes": adapter.stat().st_size if adapter.is_file() else 0,
            "base_model": base_name, "base_cache": _weight_files(base_name),
        }
    models["retrieval_encoder"] = {"model": EMBEDDING_MODEL, "revision": EMBEDDING_REVISION,
                                   "base_cache": _weight_files(EMBEDDING_MODEL, revision=EMBEDDING_REVISION)}
    return models


def inspect_host() -> dict[str, Any]:
    import psutil
    import torch

    memory = psutil.virtual_memory()
    gpu = []
    for index in range(torch.cuda.device_count()):
        free, total = torch.cuda.mem_get_info(index)
        gpu.append({"name": torch.cuda.get_device_name(index), "vram_total_bytes": total,
                    "vram_free_bytes": free})
    return {"ram_total_bytes": memory.total, "ram_available_bytes": memory.available,
            "torch_version": torch.__version__, "cuda_available": torch.cuda.is_available(), "gpu": gpu}


def inspect_faiss() -> dict[str, Any]:
    import faiss

    index_file = ROOT / "kb_indexing/indices/faiss_arxiv.index"
    id_file = ROOT / "kb_indexing/indices/faiss_doc_ids.json"
    started = time.perf_counter()
    try:
        index = faiss.read_index(str(index_file))
        ids = json.loads(id_file.read_text(encoding="utf-8"))
        return {"readable": True, "vectors": index.ntotal, "dimensions": index.d,
                "id_count": len(ids), "ids_aligned": index.ntotal == len(ids),
                "load_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:
        return {"readable": False, "error_type": type(exc).__name__}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local resources without loading LLMs")
    parser.add_argument("--faiss", action="store_true", help="Read the real FAISS index")
    args = parser.parse_args()
    result = {"host": inspect_host(), "models": inspect_models()}
    if args.faiss:
        result["faiss"] = inspect_faiss()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
