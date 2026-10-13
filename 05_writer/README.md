# Writer Agent — bounded internal revision (Plan A)

This module turns an existing, immutable `verified_claims` pool into a cited
research report. It implements **Plan A**: generation, sentence-level critique,
and repair happen inside this node. Missing evidence never causes a graph edge,
retrieval call, `Command`, or request back to the Orchestrator.

When the report still fails after at most `MAX_INTERNAL_RETRY` local revisions,
the node returns the best valid candidate it observed with
`low_confidence_warning=true`. This is a UI/outer-layer warning, not a routing
instruction or hard failure. An empty claim pool also returns a valid empty
report and the warning immediately.

Runtime coverage guard v8 removes duplicate evidence sentences, asks both the
generator and critic to inspect the complete fixed claim pool, and falls back
to a deduplicated verbatim-claim report when every model generation attempt is
invalid. The fallback always keeps `low_confidence_warning=true`; it cannot
establish intent coverage and never retrieves or invents claims.

```text
verified_claims + intent
          |
     generate report
          |
   critique every sentence
          |
  pass? -- yes --> return report
    |
    no
    |
delete / rewrite / reselect OTHER existing claims
    |
    +---- re-critique, at most N local revisions ----+
                                                     |
                        exhausted / no repair -------+
                                  return best + warning
```

There is deliberately no `request_new_claim` action. `reselect_claims` may use
only different IDs already present in the input pool, and its implementation
rebuilds text from those claims instead of trusting model-supplied replacement
text.

## Contracts

`schemas.py` is the single contract used by data generation, validation,
training, inference and the LangGraph adapter. A claim is accepted only when it
has `verification_status="verified"`, a stable ID, evidence, source ID and a
finite confidence in `[0, 1]`.

Minimal state input:

```python
state = {
    "intent": "What evaluation protocol did the paper use?",
    "verified_claims": [
        {
            "claim_id": "paper-1:c1",
            "text": "Evaluation used five folds.",
            "evidence": "Evaluation used five folds.",
            "source_id": "paper-1:paragraph:17",
            "confidence": 1.0,
            "verification_status": "verified",
        }
    ],
}
```

The LangGraph-compatible node returns only a partial state update:

```python
{
    "final_report": {...},
    "low_confidence_warning": True | False,
    "writer_diagnostics": {
        "critique": {...},
        "internal_retries": 0,
        "warning_reasons": [...],
        "trace": [...],
    },
}
```

The current `04_factchecker/node.py` produces one decision at a time and does
not yet emit this claim-pool contract. The outer graph must aggregate only
supported decisions into `verified_claims`; do not rename a raw fact-check
decision to make the interfaces appear compatible.

Because the folder starts with a digit, import it with `importlib` or run files
as modules:

```python
import importlib
WriterNode = importlib.import_module("05_writer.node").WriterNode
result = WriterNode()(state)
```

## QASPER data: what the labels mean

[QASPER](https://huggingface.co/datasets/allenai/qasper) contains scientific
papers, information-seeking questions, answers and supporting evidence. It does
not contain native Writer reports, sentence critiques or Writer actions. The
generator therefore uses a conservative derived curriculum:

- A claim is a textual evidence span found verbatim in its annotated full-text
  paragraph. Here, `verified` means **verbatim source match**, not independent
  semantic verification.
- Report targets quote those claims exactly. They do not convert a `yes_no`
  answer into a new factual assertion. Python `False` is preserved as the
  annotated answer “No”, never treated as missing.
- Visual-only `FLOAT SELECTED` evidence, unmatched text and overlong snippets
  are omitted rather than guessed or truncated.
- Conflicting answerability/polarity annotations produce an empty claim pool.
- Negative critic examples contain an explicit reproducible synthetic marker.
- Action examples contain only `reselect_claims`, select another claim already
  in the pool, and never model an Orchestrator round trip.
- Native paper-level train/validation/test splits are preserved. Test produces
  review candidates only and never enters SFT.

The Hugging Face Parquet conversion is pinned in
`generate_training_data.py`. Generate and validate it with:

```bash
python 05_writer/generate_training_data.py
python 05_writer/validate_labels.py --data-dir 05_writer/data
```

For a quick parser check, add `--max-papers-per-split 3`. For downloaded
original QASPER JSON, repeat `--local-json` for each native split:

```bash
python 05_writer/generate_training_data.py \
  --local-json train=/path/train.json \
  --local-json validation=/path/dev.json \
  --local-json test=/path/test.json
```

Files:

- `writer_sft_raw.jsonl`: generated train and validation candidates.
- `writer_sft_validated.jsonl`: only rows accepted by code validation.
- `writer_sft_rejected.jsonl`: line, reason and rejected input.
- `writer_eval_candidates.jsonl`: held-out test candidates for annotation.
- `writer_eval_manual.jsonl`: intentionally empty until a human adds labels.

Do not claim a human faithfulness score from generated candidates. The evaluator
only calls `faithfulness_score` a gold metric when every sentence has a human
boolean label bound to the exact report SHA256. It reports exact-copy support as
a separate proxy.

## Kaggle QLoRA

The default model is `Qwen/Qwen2.5-1.5B-Instruct`. The QLoRA settings are
starting values, not a universal optimum. Official PEFT guidance uses 4-bit
NF4, prepares the model for k-bit training, and supports `all-linear` for
QLoRA-style adapters:
[PEFT quantization guide](https://huggingface.co/docs/peft/v0.14.0/developer_guides/quantization).
This project also uses the model's chat template and completion-only loss.

On Kaggle, enable one GPU, add this repository and the validated JSONL as input,
then install the pinned stack. Keep Kaggle's CUDA-compatible Torch when it
satisfies the range:

```bash
pip install -r 05_writer/requirements-train.txt
```

First run preprocessing only. It downloads config/tokenizer, never weights:

```bash
python -m 05_writer.train_writer_qlora \
  --data 05_writer/data/writer_sft_validated.jsonl \
  --max-seq-length 1536 \
  --max-eval-examples 512 \
  --dry-run
```

The training prompt uses compact JSON output contracts while
`report_schema_validator.py` still enforces the complete runtime contract. On
the checked-in data, a local dry run with the pinned tokenizer and a 512-row
validation cap produced the following preprocessing counts. These are token
counts, not a promise about Kaggle wall-clock time:

| Prompt/model view / max length | Train kept | Train input tokens | Validation kept |
|---|---:|---:|---:|
| Previous full schema + full claims / 2048 | 7,895 | 7,596,306 | 496 / 512 |
| Compact contract + full claims / 2048 | 7,910 | 6,172,054 | 501 / 512 |
| Compact contract + `claim_id,text` / 1536 | 7,938 | 4,253,259 | 512 / 512 |

The final projection keeps the complete claim objects in Python for validation,
audit and actions, while the LLM sees only the two fields it can use. It reduced
train input tokens by 44.01% versus the reported run and dropped no train row.
A second dry run over all 3,356 native validation rows also dropped zero rows;
its longest sequence was 1,534 tokens with this pinned tokenizer.

Then run a short, clearly labelled smoke train:

```bash
python -m 05_writer.train_writer_qlora \
  --data 05_writer/data/writer_sft_validated.jsonl \
  --output-dir /kaggle/working/writer-smoke-fast-v3 \
  --max-steps 5 \
  --max-train-examples 128 \
  --max-eval-examples 32 \
  --max-seq-length 1536 \
  --batch-size 4 \
  --eval-batch-size 1 \
  --gradient-accumulation-steps 4 \
  --optimizer adamw_torch_fused \
  --no-gradient-checkpointing
```

Use `benchmark.json`, especially tokens/second and peak reserved VRAM, to
compare profiles. If the smoke run raises CUDA OOM, first remove
`--no-gradient-checkpointing`. If it still raises OOM, use `--batch-size 2`
and `--gradient-accumulation-steps 8`; the effective batch remains 16.

The default full run is staged: one epoch, no periodic validation, one final
validation pass, and an epoch-end Trainer checkpoint. This avoids assuming a
second pass improves held-out behavior and makes that pass resumable. The
adapter, tokenizer, state and training-only benchmark are saved before final
validation, so an evaluation OOM cannot discard the completed epoch. On the
reported 14.56 GiB Kaggle GPU, validation batch four was too large; the default
is now one.

```bash
python -m 05_writer.train_writer_qlora \
  --data 05_writer/data/writer_sft_validated.jsonl \
  --output-dir /kaggle/working/writer_qlora_fast_v3 \
  --max-seq-length 1536 \
  --batch-size 4 \
  --eval-batch-size 1 \
  --gradient-accumulation-steps 4 \
  --epochs 1 \
  --max-eval-examples 512 \
  --optimizer adamw_torch_fused \
  --no-gradient-checkpointing
```

Only continue to epoch two after comparing the saved validation loss and the
frozen Writer evaluation suite. Resume from the actual epoch-end checkpoint
directory printed by Trainer, preserving the prompt version, optimizer,
checkpointing mode, data, sequence length, sample caps, seed, batch size and
gradient accumulation:

```bash
python -m 05_writer.train_writer_qlora \
  --data 05_writer/data/writer_sft_validated.jsonl \
  --output-dir /kaggle/working/writer_qlora_fast_v3 \
  --max-seq-length 1536 \
  --batch-size 4 \
  --eval-batch-size 1 \
  --gradient-accumulation-steps 4 \
  --epochs 2 \
  --max-eval-examples 512 \
  --optimizer adamw_torch_fused \
  --no-gradient-checkpointing \
  --resume-from-checkpoint /kaggle/working/writer_qlora_fast_v3/checkpoint-<actual-step>
```

Do not resume a checkpoint created with the previous full-schema prompt. The
manifest now records a training-contract version and rejects that unsafe mix;
start in a new output directory such as `writer_qlora_fast_v3`.

The trainer deliberately uses one visible GPU, NF4 + double quantization,
`all-linear` LoRA, optional non-reentrant gradient checkpointing, dynamic padding, no
cross-example packing and no truncation. An overlength example is excluded as a
whole so neither evidence nor target JSON is cut. It saves:

- adapter and tokenizer;
- `run_manifest.json` with resolved model revision, package versions, data hash,
  preprocessing counts and configuration;
- `benchmark.json` with measured wall time, throughput and peak CUDA memory.

Benchmark training counters refer only to the current `train()` invocation.
After a resume from an already completed checkpoint, zero optimizer steps run;
`train_metrics` is then null rather than a misleading zero loss. Final
validation metrics remain valid for the loaded adapter.

Only those measurements describe actual Kaggle performance. Batch size,
sequence length and checkpoint frequency should be tuned from a smoke run on
the selected Kaggle GPU; no fixed runtime is promised here.

Merge into a new, non-nested output directory after training:

```bash
python -m 05_writer.merge_lora_weights \
  --adapter /kaggle/working/writer_qlora \
  --output /kaggle/working/writer_merged \
  --device cpu
```

The merger loads the recorded base revision without 4-bit quantization and uses
PEFT `safe_merge=True`. Evaluate the merged artifact again; quantized adapter
inference and a merged full-precision artifact are not assumed identical.

## Inference and evaluation

`HFJsonBackend` performs one greedy JSON generation per component. It rejects
JSON fences, trailing prose, duplicate keys, non-finite numbers and context
overflow. It never silently drops claims. All retry accounting belongs to
`WriterLoopController`.

For the current verbatim-evidence contract, `Critic` downgrades a model's
`supported` verdict to `uncertain` when the sentence is not an exact copy of
its cited claims. This prevents unvalidated paraphrases, changed numbers, and
negation flips from passing solely on the model's judgement. Exact copying
still does not establish relevance to the intent or semantic faithfulness.

If the model proposes an invalid action, the internal loop may fall back to a
deterministic rewrite that copies the sentence's existing cited claims exactly.
It records `action_selection_failed` and keeps `low_confidence_warning=true`
even if a later critique accepts the rewrite. Unknown claim IDs in generated
reports remain invalid; the writer never guesses or repairs citations.

Quick CPU plumbing check:

```bash
python 05_writer/notebooks/00_quick_inference_check.py
python -m unittest discover -s 05_writer/tests -v
```

The no-model baseline copies claims exactly and marks intent coverage as
unassessed, so `low_confidence_warning` stays true. This is intentional: string
identity can check citation consistency, but cannot prove that the report fully
answers the user's intent.

Evaluate saved predictions:

```bash
python -m 05_writer.eval_writer \
  --data 05_writer/data/writer_eval_manual.jsonl \
  --predictions /path/writer_predictions.jsonl \
  --output /path/writer_eval_metrics.json
```

Metrics are schema validity rate, independently reviewed sentence
faithfulness, exact-copy support proxy, empty-report rate, warning-field
coverage and `low_confidence_warning` percentage/reasons.
