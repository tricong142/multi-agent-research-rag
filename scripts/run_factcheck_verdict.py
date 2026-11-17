"""Run a blind JSON-verdict pilot with Qwen2.5 3B or 7B NF4 on a CUDA host."""
import argparse
import hashlib
from importlib import import_module
import json
from pathlib import Path
import time


MODELS = {
    '3b': ('Qwen/Qwen2.5-3B-Instruct', 'aa8e72537993ba99e69dfaafa59ed015b17504d1'),
    '7b': ('Qwen/Qwen2.5-7B-Instruct', 'a09a35458c702b33eeacc393d103063234e8bc28'),
}
NLI_MODEL = 'cross-encoder/nli-deberta-v3-large'
verdict = import_module('04_factchecker.inference.semantic_verdict')
ledger = import_module('04_factchecker.inference.source_ledger')
comparison = import_module('04_factchecker.inference.source_comparison')


def load_nli(revision, offline):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    options = dict(revision=revision, local_files_only=offline, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL, **options)
    model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL, use_safetensors=True, **options).eval()
    labels = {int(i): v.casefold() for i, v in model.config.id2label.items()}
    if set(labels.values()) != {'entailment', 'contradiction', 'neutral'}:
        raise ValueError('Unexpected NLI label mapping')
    limit = min(tokenizer.model_max_length, model.config.max_position_embeddings)

    def score(evidence, claim):
        tokens = tokenizer(evidence, claim, return_tensors='pt', truncation=False)
        if tokens['input_ids'].shape[-1] > limit:
            return None
        with torch.inference_mode():
            scores = model(**tokens).logits[0].softmax(dim=-1).tolist()
        return {label: scores[i] for i, label in labels.items()}

    return score


def read_inputs(raw):
    cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if (not cases or any(not isinstance(row, dict) or set(row) != {'id', 'claim', 'context'}
            or any(not isinstance(v, str) or not v.strip() for v in row.values()) for row in cases)
            or len({row['id'] for row in cases}) != len(cases)):
        raise ValueError('Blind inputs require unique id, claim and context fields')
    return cases


def assess_case(case, generate, *, evidence_format, source_id_policy=ledger.LEGACY_POLICY):
    claim, context = case['claim'], case['context']
    if evidence_format == 'quotes':
        proposal = verdict.validate(generate(verdict.messages(claim, context)), context)
        return proposal, proposal, None
    segments = verdict.source_segments(context)
    if source_id_policy == comparison.POLICY:
        proof = comparison.compare_scoped_table_value(claim, context, segments)
        if proof:
            label, ids, reason = proof
            final = verdict.resolve_segments(dict(label=label, evidence_ids=ids, confidence=None, reasoning=reason),
                                             segments)
            return final, final, dict(label=label, method='scoped_table_value', reasoning=reason)
    raw = generate(verdict.segment_messages(verdict.SOURCE_ID_PROMPT, claim, segments))
    proposal = verdict.resolve_segments(raw, segments)
    verify = {ledger.LEGACY_POLICY: verdict.check_segments, ledger.POLICY: verdict.check_source_ledger,
              comparison.POLICY: verdict.check_grounded_r8}[source_id_policy]
    final, check = verify(proposal, claim, segments, generate, context=context)
    return proposal, final, check


def run(args):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError('This NF4 pilot needs CUDA')
    decoder = import_module('04_factchecker.inference.atomic_decoding')
    atomic = import_module('04_factchecker.inference.atomic_verifier')
    raw = args.inputs.read_bytes()
    cases = read_inputs(raw)
    repo, revision = MODELS[args.model]
    if args.adapter:
        if args.evidence_format != 'quotes':
            raise ValueError('Existing verdict adapters use --evidence-format quotes')
        info = json.loads((args.adapter.parent / 'run_info.json').read_bytes())
        if (info['base_model'], info['base_revision'], info['verdict_chat']) != (repo, revision, True):
            raise ValueError('Adapter does not belong to the selected verdict model and revision')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    source_ids = args.evidence_format == 'ids'
    prompt = verdict.SOURCE_ID_PROMPT if source_ids else verdict.SYSTEM_PROMPT
    schema = verdict.segment_schema(()) if source_ids else verdict.schema()
    stamp = dict(model=repo, revision=revision, input_sha256=hashlib.sha256(raw).hexdigest(),
                 quantization='NF4', dtype='float16', gpu=torch.cuda.get_device_name(0),
                 torch_version=torch.__version__, seed=42, max_new_tokens=args.max_new_tokens,
                 timeout_seconds=args.timeout_seconds,
                 evidence_format=args.evidence_format,
                 source_id_check_policy=args.source_id_policy if source_ids else None,
                 numeric_claim_prompt_sha256=hashlib.sha256(verdict.NUMERIC_CLAIM_PROMPT.encode()).hexdigest()
                 if source_ids else None,
                 numeric_source_prompt_sha256=hashlib.sha256(verdict.NUMERIC_SOURCE_PROMPT.encode()).hexdigest()
                 if source_ids else None,
                 schema_sha256=decoder.schema_sha256(schema),
                 evidence_check_schema_sha256=decoder.schema_sha256(verdict.segment_schema()) if source_ids else None,
                 evidence_check_prompt_sha256=hashlib.sha256(verdict.EVIDENCE_CHECK_PROMPT.encode()).hexdigest()
                 if source_ids else None,
                 adapter_sha256=hashlib.sha256((args.adapter / 'adapter_model.safetensors').read_bytes()).hexdigest()
                 if args.adapter else None,
                 prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                 nli_model=NLI_MODEL if args.nli_revision else None, nli_revision=args.nli_revision,
                 nli_threshold=args.nli_threshold if args.nli_revision else None)
    if source_ids and args.source_id_policy == ledger.POLICY:
        stamp.update(ledger_prompt_sha256=hashlib.sha256(ledger.LEDGER_PROMPT.encode()).hexdigest(),
                     ledger_schema_sha256=decoder.schema_sha256(ledger.schema(('S1',))),
                     relation_prompt_sha256=hashlib.sha256(ledger.RELATION_PROMPT.encode()).hexdigest(),
                     relation_schema_sha256=decoder.schema_sha256(ledger.relation_schema()))
    if source_ids and args.source_id_policy == comparison.POLICY:
        stamp.update(recovery_prompt_sha256=hashlib.sha256(comparison.RECOVERY_PROMPT.encode()).hexdigest(),
                     recovery_schema_sha256=decoder.schema_sha256(comparison.recovery_schema(('S1',))),
                     fixed_clause_prompt_sha256=hashlib.sha256(ledger.FIXED_CLAUSE_PROMPT.encode()).hexdigest(),
                     fixed_clause_schema_sha256=decoder.schema_sha256(ledger.fixed_clause_schema('C1', ('S1',))),
                     clause_retry_prompt_sha256=hashlib.sha256(ledger.CLAUSE_RETRY_PROMPT.encode()).hexdigest(),
                     relation_prompt_sha256=hashlib.sha256(ledger.RELATION_PROMPT.encode()).hexdigest(),
                     relation_schema_sha256=decoder.schema_sha256(ledger.relation_schema()))
    (args.output_dir / 'provenance.json').write_text(json.dumps(stamp, indent=2), encoding='utf-8')
    options = dict(revision=revision, local_files_only=not args.online_model_downloads, trust_remote_code=False)
    torch.manual_seed(stamp['seed'])
    torch.cuda.reset_peak_memory_stats(0)
    tokenizer = AutoTokenizer.from_pretrained(repo, **options)
    model = AutoModelForCausalLM.from_pretrained(repo, device_map={'': 0}, dtype=torch.float16,
        use_safetensors=True, quantization_config=BitsAndBytesConfig(load_in_4bit=True,
        bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16), **options).eval()
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False).eval()
    nli = load_nli(args.nli_revision, not args.online_model_downloads) if args.nli_revision else None
    backend = decoder.ConstrainedAtomicBackend(model, tokenizer)
    with (args.output_dir / 'predictions.jsonl').open('x', encoding='utf-8') as predictions:
        for case in cases:
            start = time.monotonic()
            generation = []
            backend.on_generation = generation.append
            try:
                deadline = start + args.timeout_seconds
                with backend.generation_deadline(deadline):
                    def generate(messages):
                        return backend.generate_json(messages, max_new_tokens=args.max_new_tokens)

                    original, checked, check = assess_case(case, generate, evidence_format=args.evidence_format,
                                                           source_id_policy=args.source_id_policy)
                final, scores = verdict.veto(checked, case['claim'], nli, args.nli_threshold) if nli else (checked, None)
                if time.monotonic() >= deadline:
                    raise atomic.CaseDeadlineExceeded()
                result = dict(status='completed', assessed_label=final['label'], verdict=final,
                              proposed_verdict=original, evidence_check=check, nli_scores=scores)
            except (ValueError, atomic.CaseDeadlineExceeded) as exc:
                result = dict(status='incomplete', assessed_label=None, error_type=type(exc).__name__,
                              error_detail=str(exc))
            result.update(generation=generation, elapsed_ms=round((time.monotonic() - start) * 1000, 2))
            predictions.write(json.dumps(dict(example_id=case['id'], result=result), ensure_ascii=False) + '\n')
            predictions.flush()
    memory = dict(peak_allocated_bytes=torch.cuda.max_memory_allocated(0), peak_reserved_bytes=torch.cuda.max_memory_reserved(0))
    (args.output_dir / 'summary.json').write_text(json.dumps(dict(cases=len(cases), **memory), indent=2), encoding='utf-8')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--inputs', type=Path, required=True)
    cli.add_argument('--output-dir', type=Path, required=True)
    cli.add_argument('--model', choices=MODELS, default='7b')
    cli.add_argument('--evidence-format', choices=('ids', 'quotes'), default='ids')
    cli.add_argument('--source-id-policy', choices=(ledger.LEGACY_POLICY, ledger.POLICY, comparison.POLICY),
                     default=ledger.LEGACY_POLICY)
    cli.add_argument('--adapter', type=Path, help='Optional final/ folder from verdict QLoRA training')
    cli.add_argument('--online-model-downloads', action='store_true')
    cli.add_argument('--nli-revision', help='Optional full SHA for the NLI cross-encoder')
    cli.add_argument('--nli-threshold', type=float, default=.85)
    cli.add_argument('--max-new-tokens', type=int, default=512)
    cli.add_argument('--timeout-seconds', type=int, default=180)
    args = cli.parse_args()
    if (args.max_new_tokens < 1 or args.timeout_seconds < 1 or not 0 <= args.nli_threshold <= 1
            or args.nli_revision and (len(args.nli_revision) != 40 or not all(c in '0123456789abcdef' for c in args.nli_revision))):
        cli.error('Invalid limits or NLI revision')
    run(args)
