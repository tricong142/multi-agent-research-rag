"""Merge an adapter into its original, non-quantized base in a NEW directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "05_writer"

from .config import ADAPTER_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, default=ADAPTER_DIR)
    parser.add_argument("--output", type=Path, default=ADAPTER_DIR.parent / "writer_merged")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu", help="CPU is slower but avoids GPU OOM.")
    parser.add_argument("--dtype", choices=("auto", "float32", "float16", "bfloat16"), default="auto")
    parser.add_argument("--local-files-only", action="store_true")
    args = parser.parse_args(argv)
    adapter, output = args.adapter.resolve(), args.output.resolve()
    if output == adapter or adapter in output.parents or output in adapter.parents:
        raise ValueError("Merged output must be separate from the adapter directory (not parent or child).")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; existing artifacts are never overwritten.")
    adapter_config_path = adapter / "adapter_config.json"
    if not adapter_config_path.is_file():
        raise FileNotFoundError(f"No adapter_config.json at {adapter}")
    adapter_config = json.loads(adapter_config_path.read_text(encoding="utf-8"))
    manifest_path = adapter / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    base_model = adapter_config.get("base_model_name_or_path")
    if not base_model:
        raise ValueError("Adapter does not identify its base model.")
    revision = manifest.get("resolved_model_revision") or adapter_config.get("revision")
    if not revision:
        raise ValueError("Adapter must record the original base revision; refusing an untracked merge.")
    if manifest and manifest["model_config"]["base_model"] != base_model:
        raise ValueError("Adapter base model disagrees with training manifest.")
    if adapter_config.get("revision") and adapter_config["revision"] != revision:
        raise ValueError("Adapter revision disagrees with training manifest.")

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable. Use --device cpu or enable a GPU.")
    if args.dtype == "auto":
        dtype = torch.float32 if args.device == "cpu" else (
            torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
        )
    else:
        dtype = getattr(torch, args.dtype)
    # Deliberately do not pass BitsAndBytesConfig: merging NF4 weights introduces
    # another rounding path. Load the original full-precision checkpoint instead.
    base = AutoModelForCausalLM.from_pretrained(
        base_model, revision=revision, torch_dtype=dtype,
        device_map={"": args.device}, low_cpu_mem_usage=True,
        trust_remote_code=False, local_files_only=args.local_files_only,
    )
    model = PeftModel.from_pretrained(base, str(adapter), is_trainable=False)
    model.eval()
    merged = model.merge_and_unload(safe_merge=True)
    merged.config.use_cache = True
    tokenizer = AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=False, local_files_only=True)
    output.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(output, safe_serialization=True, max_shard_size="2GB")
    tokenizer.save_pretrained(output)
    merge_manifest = {
        "adapter": str(adapter), "base_model": base_model, "base_revision": revision,
        "dtype": str(dtype), "safe_merge": True,
        "note": "Run held-out evaluation before deployment; quantized-adapter and merged outputs can differ.",
    }
    (output / "merge_manifest.json").write_text(
        json.dumps(merge_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"merged_model": str(output), **merge_manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
