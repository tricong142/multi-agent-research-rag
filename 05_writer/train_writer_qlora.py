"""Single-GPU QLoRA for Kaggle; run --help without loading GPU libraries.

Example: python -m 05_writer.train_writer_qlora --max-steps 5
The measured runtime is reported after execution, never guessed in advance.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "05_writer"

from .config import ADAPTER_DIR, DATA_DIR, ModelConfig, TrainingConfig
from .prompts import TRAINING_CONTRACT_VERSION
from .training_utils import CompletionCollator, load_training_splits, prepare_examples, sha256_file


def build_parser() -> argparse.ArgumentParser:
    model, training = ModelConfig(), TrainingConfig()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_DIR / "writer_sft_validated.jsonl")
    parser.add_argument("--output-dir", type=Path, default=ADAPTER_DIR)
    parser.add_argument("--base-model", default=model.base_model)
    parser.add_argument("--revision", default=model.revision, help="A Hub commit SHA is preferred for reproducibility.")
    parser.add_argument("--max-seq-length", type=int, default=training.max_seq_length)
    parser.add_argument("--batch-size", type=int, default=training.per_device_train_batch_size)
    parser.add_argument("--eval-batch-size", type=int, default=training.per_device_eval_batch_size)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=training.gradient_accumulation_steps)
    parser.add_argument("--epochs", type=float, default=training.num_train_epochs)
    parser.add_argument("--learning-rate", type=float, default=training.learning_rate)
    parser.add_argument("--seed", type=int, default=training.seed)
    parser.add_argument("--eval-steps", type=int, default=training.eval_steps)
    parser.add_argument("--save-steps", type=int, default=training.save_steps)
    parser.add_argument("--eval-strategy", choices=("no", "steps", "epoch"), default=training.eval_strategy)
    parser.add_argument("--save-strategy", choices=("steps", "epoch"), default=training.save_strategy)
    parser.add_argument(
        "--optimizer", choices=("adamw_torch_fused", "paged_adamw_8bit"), default=training.optimizer,
        help="Fused AdamW is usually faster; use paged AdamW if optimizer memory is constrained.",
    )
    parser.add_argument("--max-steps", type=int, default=-1, help="Positive value overrides epochs; 5 is a smoke run.")
    parser.add_argument("--max-train-examples", type=int, help="Optional smoke/benchmark cap AFTER native splitting.")
    parser.add_argument("--max-eval-examples", type=int, help="Optional validation cap AFTER native splitting.")
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument("--no-gradient-checkpointing", action="store_true", help="Benchmark only when VRAM permits.")
    parser.add_argument("--dry-run", action="store_true", help="Validate/tokenize data on CPU; no model weights or training.")
    parser.add_argument("--local-files-only", action="store_true", help="Require model/tokenizer already cached locally.")
    return parser


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in (
        "max_seq_length", "batch_size", "eval_batch_size",
        "gradient_accumulation_steps", "eval_steps", "save_steps",
    ):
        if getattr(args, name) < 1:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.max_seq_length % 8:
        raise ValueError("--max-seq-length must be a multiple of 8 for aligned dynamic padding.")
    if args.epochs <= 0 or args.learning_rate <= 0 or args.max_steps == 0 or args.max_steps < -1:
        raise ValueError("epochs/learning-rate must be positive; max-steps must be -1 or positive.")
    for name in ("max_train_examples", "max_eval_examples"):
        if getattr(args, name) is not None and getattr(args, name) < 1:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if int(os.environ.get("WORLD_SIZE", "1")) != 1:
        raise ValueError("This Kaggle entry point uses one GPU; launch one Python process, not torchrun/DDP.")

    model_config = replace(ModelConfig(), base_model=args.base_model, revision=args.revision)
    train_config = replace(
        TrainingConfig(), max_seq_length=args.max_seq_length,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_train_epochs=args.epochs, learning_rate=args.learning_rate, seed=args.seed,
        gradient_checkpointing=not args.no_gradient_checkpointing,
        eval_steps=args.eval_steps, save_steps=args.save_steps,
        eval_strategy=args.eval_strategy, save_strategy=args.save_strategy,
        optimizer=args.optimizer,
    )
    train_rows, eval_rows = load_training_splits(args.data)
    # Shuffle before smoke caps: generator order can otherwise bias task mix.
    import random

    rng = random.Random(train_config.seed)
    rng.shuffle(train_rows)
    rng.shuffle(eval_rows)
    train_rows = train_rows[: args.max_train_examples]
    eval_rows = eval_rows[: args.max_eval_examples]
    data_hash = sha256_file(args.data)
    effective_revision = model_config.revision
    output_dir = args.output_dir.resolve()
    manifest_path = output_dir / "run_manifest.json"
    caps = {"train": args.max_train_examples, "validation": args.max_eval_examples}
    resume_global_step = 0
    if args.resume_from_checkpoint:
        if output_dir not in args.resume_from_checkpoint.resolve().parents:
            raise ValueError("Resume checkpoint must belong to the original output directory.")
        if not (args.resume_from_checkpoint / "trainer_state.json").is_file():
            raise ValueError("Resume requires a Trainer checkpoint containing trainer_state.json.")
        resume_global_step = int(json.loads(
            (args.resume_from_checkpoint / "trainer_state.json").read_text(encoding="utf-8")
        )["global_step"])
        if not manifest_path.is_file():
            raise ValueError("Resume requires the original output-dir/run_manifest.json.")
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("training_contract_version") != TRAINING_CONTRACT_VERSION:
            raise ValueError("Resume prompt/training contract differs from the original run.")
        if previous["data_sha256"] != data_hash or previous["model_config"] != asdict(model_config):
            raise ValueError("Resume data/model configuration differs from the original run.")
        if previous["training_config"]["max_seq_length"] != args.max_seq_length or previous["example_caps"] != caps:
            raise ValueError("Resume must use the same sequence length and example caps.")
        ordering_fields = (
            "seed", "per_device_train_batch_size", "gradient_accumulation_steps",
            "gradient_checkpointing", "optimizer",
        )
        if any(previous["training_config"].get(key) != asdict(train_config)[key] for key in ordering_fields):
            raise ValueError(
                "Resume must preserve seed, batch size, gradient accumulation, "
                "gradient checkpointing and optimizer."
            )
        effective_revision = previous["resolved_model_revision"]
    elif not args.dry_run and output_dir.exists():
        if any(path.name not in {".gitkeep", ".gitignore"} for path in output_dir.iterdir()):
            raise ValueError("Output directory is nonempty; use a new directory or --resume-from-checkpoint.")

    # Prevent Trainer's implicit DataParallel on Kaggle's two-T4 configuration.
    # This affects only this script process. Select a different GPU before launch
    # with CUDA_VISIBLE_DEVICES; if a list was supplied, use its first GPU.
    os.environ["CUDA_VISIBLE_DEVICES"] = os.environ.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0]
    # Lazy imports keep schema/preprocessing tests and --help lightweight.
    import torch
    from transformers import AutoConfig, AutoTokenizer, set_seed

    if not args.dry_run and not torch.cuda.is_available():
        raise RuntimeError("QLoRA requires a CUDA GPU. Enable a Kaggle GPU or use --dry-run for CPU preprocessing.")
    if not args.dry_run and torch.cuda.device_count() != 1:
        raise RuntimeError("Run this script in a fresh process with CUDA_VISIBLE_DEVICES selecting exactly one GPU.")
    set_seed(train_config.seed)
    base_config = AutoConfig.from_pretrained(
        model_config.base_model, revision=effective_revision,
        trust_remote_code=False, local_files_only=args.local_files_only,
    )
    resolved_revision = getattr(base_config, "_commit_hash", None) or effective_revision
    tokenizer = AutoTokenizer.from_pretrained(
        model_config.base_model, revision=resolved_revision,
        trust_remote_code=False, local_files_only=args.local_files_only,
    )
    if not tokenizer.chat_template:
        raise ValueError("Base tokenizer must contain an explicit chat template.")
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is None:
            raise ValueError("Tokenizer has neither pad nor EOS token.")
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    train_features, train_stats = prepare_examples(train_rows, tokenizer, train_config.max_seq_length)
    eval_features, eval_stats = prepare_examples(eval_rows, tokenizer, train_config.max_seq_length)
    preparation = {"train": train_stats, "validation": eval_stats}
    print(json.dumps({"preprocessing": preparation}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments

    device_index = torch.cuda.current_device()
    bf16 = torch.cuda.get_device_capability(device_index)[0] >= 8 and torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if bf16 else torch.float16
    quantization = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_config.base_model, revision=resolved_revision,
        quantization_config=quantization, torch_dtype=compute_dtype,
        attn_implementation=model_config.attn_implementation,
        device_map={"": device_index}, trust_remote_code=False,
        local_files_only=args.local_files_only,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=train_config.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    lora_config = LoraConfig(
        r=model_config.lora_r, lora_alpha=model_config.lora_alpha,
        lora_dropout=model_config.lora_dropout, target_modules=model_config.target_modules,
        bias="none", task_type="CAUSAL_LM", revision=resolved_revision,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "training_contract_version": TRAINING_CONTRACT_VERSION,
        "model_config": asdict(model_config), "training_config": asdict(train_config),
        "resolved_model_revision": resolved_revision, "data_path": str(args.data.resolve()),
        "data_sha256": data_hash, "example_caps": caps, "max_steps": args.max_steps,
        "preprocessing": preparation,
        "resume_from_checkpoint": str(args.resume_from_checkpoint) if args.resume_from_checkpoint else None,
        "versions": {name: importlib.metadata.version(name) for name in (
            "torch", "transformers", "peft", "accelerate", "bitsandbytes", "datasets"
        )},
        "gpu": torch.cuda.get_device_name(device_index), "compute_dtype": str(compute_dtype),
        "cuda_version": torch.version.cuda, "world_size": 1,
        "training_policy": "native train only; native validation for loss; test/manual held out; completion-only; no packing",
    }
    _write_json(manifest_path, manifest)
    training_args = TrainingArguments(
        output_dir=str(output_dir), num_train_epochs=train_config.num_train_epochs,
        max_steps=args.max_steps, per_device_train_batch_size=train_config.per_device_train_batch_size,
        per_device_eval_batch_size=train_config.per_device_eval_batch_size,
        gradient_accumulation_steps=train_config.gradient_accumulation_steps,
        learning_rate=train_config.learning_rate, warmup_ratio=train_config.warmup_ratio,
        weight_decay=train_config.weight_decay, lr_scheduler_type="cosine", max_grad_norm=1.0,
        bf16=bf16, fp16=not bf16, tf32=torch.cuda.get_device_capability(device_index)[0] >= 8,
        optim=train_config.optimizer, gradient_checkpointing=train_config.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=train_config.logging_steps, logging_first_step=True,
        eval_strategy=train_config.eval_strategy, eval_steps=train_config.eval_steps,
        save_strategy=train_config.save_strategy, save_steps=train_config.save_steps,
        save_total_limit=2, save_safetensors=True, prediction_loss_only=True,
        report_to="none", seed=train_config.seed, data_seed=train_config.seed,
        dataloader_num_workers=0, dataloader_pin_memory=True,
        group_by_length=True, remove_unused_columns=False, label_names=["labels"],
    )

    class MeasuredTrainer(Trainer):
        """Count actual training batches, excluding validation and resumed history."""
        seen_examples = 0
        seen_input_tokens = None
        seen_supervised_tokens = None

        def training_step(self, model, inputs, num_items_in_batch=None):
            # Reductions stay on the GPU; do not synchronize every microbatch.
            self.seen_examples += int(inputs["input_ids"].shape[0])
            input_count = inputs["attention_mask"].sum().detach()
            supervised_count = (inputs["labels"][:, 1:] != -100).sum().detach()
            self.seen_input_tokens = input_count if self.seen_input_tokens is None else self.seen_input_tokens + input_count
            self.seen_supervised_tokens = supervised_count if self.seen_supervised_tokens is None else self.seen_supervised_tokens + supervised_count
            return super().training_step(model, inputs, num_items_in_batch)

    trainer = MeasuredTrainer(
        model=model, args=training_args,
        train_dataset=Dataset.from_list(train_features), eval_dataset=Dataset.from_list(eval_features),
        data_collator=CompletionCollator(tokenizer.pad_token_id), processing_class=tokenizer,
    )
    torch.cuda.synchronize(device_index)
    torch.cuda.reset_peak_memory_stats(device_index)
    started = time.perf_counter()
    result = trainer.train(
        resume_from_checkpoint=str(args.resume_from_checkpoint) if args.resume_from_checkpoint else None
    )
    torch.cuda.synchronize(device_index)
    elapsed = time.perf_counter() - started
    peak_allocated = torch.cuda.max_memory_allocated(device_index)
    peak_reserved = torch.cuda.max_memory_reserved(device_index)
    # Save the trained adapter before validation: an evaluation OOM must not
    # discard a completed training run.
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(output_dir)
    trainer.save_state()
    input_tokens = int(trainer.seen_input_tokens.item()) if trainer.seen_input_tokens is not None else 0
    supervised_tokens = int(trainer.seen_supervised_tokens.item()) if trainer.seen_supervised_tokens is not None else 0
    final_global_step = int(trainer.state.global_step)
    steps_this_invocation = final_global_step - resume_global_step
    benchmark = {
        "train_wall_seconds": elapsed,
        "timing_scope": "this train() invocation including periodic eval/checkpoints; excludes loading, preprocessing, final eval/save",
        "resume_global_step": resume_global_step,
        "final_global_step": final_global_step,
        "optimizer_steps_this_invocation": steps_this_invocation,
        "train_metrics_scope": "this train() invocation only; never cumulative across resumes",
        "examples_processed": trainer.seen_examples, "non_padding_input_tokens_processed": input_tokens,
        "supervised_tokens_processed": supervised_tokens,
        "examples_per_second": trainer.seen_examples / elapsed,
        "non_padding_input_tokens_per_second": input_tokens / elapsed,
        "supervised_tokens_per_second": supervised_tokens / elapsed,
        "peak_cuda_allocated_gib": peak_allocated / 1024**3,
        "peak_cuda_reserved_gib": peak_reserved / 1024**3,
        "train_metrics": result.metrics if steps_this_invocation else None,
        "validation_metrics": None,
    }
    _write_json(output_dir / "benchmark.json", benchmark)
    torch.cuda.empty_cache()
    benchmark["validation_metrics"] = trainer.evaluate()
    _write_json(output_dir / "benchmark.json", benchmark)
    print(json.dumps(benchmark, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
