"""Merge the trained Fact-Checker LoRA adapter on Kaggle or locally."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path


def remove_incompatible_torchao() -> None:
    """PEFT treats an installed-but-old torchao as fatal; merge does not need it."""
    try:
        installed = importlib.metadata.version("torchao")
    except importlib.metadata.PackageNotFoundError:
        return

    from packaging.version import Version

    if Version(installed) >= Version("0.16.0"):
        return
    if "torchao" in sys.modules or any(name.startswith("torchao.") for name in sys.modules):
        raise RuntimeError(
            f"torchao {installed} is already loaded and PEFT requires >=0.16.0. "
            "Run `%pip uninstall -y torchao`, restart the Kaggle session, then rerun."
        )
    print(
        f"[setup] Removing optional incompatible torchao {installed}; "
        "this LoRA merge does not use TorchAO."
    )
    subprocess.check_call(
        [sys.executable, "-m", "pip", "uninstall", "--yes", "torchao"]
    )
    importlib.invalidate_caches()


def find_adapter() -> Path:
    preferred = Path("/kaggle/input/datasets/trcng23/finetune")
    preferred_configs = sorted(preferred.rglob("adapter_config.json")) if preferred.exists() else []
    if len(preferred_configs) == 1:
        return preferred_configs[0].parent
    if len(preferred_configs) > 1:
        choices = "\n".join(f"  - {path.parent}" for path in preferred_configs)
        raise RuntimeError(f"Multiple adapters found below {preferred}:\n{choices}")
    roots = [Path("/kaggle/input"), Path.cwd()]
    found = sorted(
        {
            config_file.parent.resolve()
            for root in roots
            if root.exists()
            for config_file in root.rglob("adapter_config.json")
        },
        key=str,
    )
    if len(found) == 1:
        return found[0]
    if not found:
        if preferred.exists():
            visible = sorted(
                str(path.relative_to(preferred))
                for path in preferred.rglob("*")
                if path.is_file()
            )[:100]
            inventory = "\n".join(f"  - {name}" for name in visible) or "  (empty directory)"
        else:
            inventory = f"  directory does not exist: {preferred}"
        raise FileNotFoundError(
            "Cannot find adapter_config.json anywhere under /kaggle/input.\n"
            f"Inspected preferred dataset: {preferred}\n"
            f"Files found there:\n{inventory}\n\n"
            "A valid PEFT adapter must contain BOTH adapter_config.json and "
            "adapter_model.safetensors (or adapter_model.bin). Upload the complete "
            "factchecker_qlora/final directory; weights alone cannot be merged safely."
        )
    choices = "\n".join(f"  - {path}" for path in found)
    raise RuntimeError(f"Multiple adapters found; pass --adapter explicitly:\n{choices}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path)
    parser.add_argument(
        "--base-model",
        help="Optional override. By default read from adapter_config.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/kaggle/working/factchecker_merged")
        if Path("/kaggle").exists()
        else Path("checkpoints/factchecker_merged"),
    )
    if "ipykernel" in sys.modules:
        args, unknown = parser.parse_known_args()
        if unknown:
            print(f"[args] Ignoring Jupyter kernel arguments: {unknown}")
        return args
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    adapter = (args.adapter or find_adapter()).resolve()
    adapter_config_path = adapter / "adapter_config.json"
    adapter_weights = list(adapter.glob("adapter_model.*"))
    if not adapter_config_path.is_file() or not adapter_weights:
        raise FileNotFoundError(
            f"Invalid adapter directory {adapter}: adapter_config.json or weights missing"
        )

    adapter_config = json.loads(adapter_config_path.read_text(encoding="utf-8"))
    trained_base = adapter_config.get("base_model_name_or_path")
    base_model = args.base_model or trained_base
    if not base_model:
        raise ValueError("base_model_name_or_path is absent; pass --base-model explicitly")
    if args.base_model and trained_base and args.base_model != trained_base:
        raise ValueError(
            f"Refusing mismatched base model: adapter was trained from {trained_base!r}, "
            f"but --base-model is {args.base_model!r}"
        )

    remove_incompatible_torchao()

    try:
        import torch
        import transformers
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Install torch, transformers, peft and accelerate") from exc

    # Qwen 7B FP16 is about 15 GB, so it cannot safely fit a 14.56-GiB T4.
    # Merge on system RAM to avoid GPU OOM.
    dtype = torch.float16
    print(f"[merge] adapter={adapter}")
    print(f"[merge] trained base model={trained_base}")
    print(f"[merge] output={args.output.resolve()}")
    print("[merge] device=CPU, dtype=float16")

    tokenizer_source = adapter if any(adapter.glob("tokenizer*")) else base_model
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source, trust_remote_code=True)
    load_kwargs = {
        "device_map": {"": "cpu"},
        "low_cpu_mem_usage": True,
        "trust_remote_code": True,
    }
    if int(transformers.__version__.split(".", 1)[0]) >= 5:
        load_kwargs["dtype"] = dtype
    else:
        load_kwargs["torch_dtype"] = dtype
    base = AutoModelForCausalLM.from_pretrained(base_model, **load_kwargs)
    peft_model = PeftModel.from_pretrained(base, str(adapter), is_trainable=False)
    merged = peft_model.merge_and_unload(progressbar=True, safe_merge=True)

    args.output.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(
        args.output,
        safe_serialization=True,
        max_shard_size="4GB",
    )
    tokenizer.save_pretrained(args.output)

    weight_files = sorted(args.output.glob("*.safetensors"))
    if not (args.output / "config.json").is_file() or not weight_files:
        raise RuntimeError("Merge finished but the saved model is incomplete")
    size_gib = sum(path.stat().st_size for path in weight_files) / 1024**3
    print(f"[done] Saved {len(weight_files)} weight shard(s), {size_gib:.2f} GiB")
    print(f"[done] Merged model: {args.output}")


if __name__ == "__main__":
    main()
