"""Offline feasibility of frozen v8 schemas with the real shared Qwen tokenizer."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_rag.evaluation import evaluate_atomic_verifier as runner
from research_rag.tests.test_atomic_decoding import Sequence
from research_rag.tests.test_atomic_assessment_v8 import AssessmentRepairTests
from transformers import AutoTokenizer


def main():
    criteria, *_ = runner.load_frozen(runner.CRITERIA)
    baseline = json.loads((runner.CRITERIA.parent / criteria['baseline_file']).read_text())
    folder = ROOT / '04_factchecker/checkpoints/factchecker_merged'
    for name, digest in baseline['model_metadata']['shared_tokenizer_files'].items():
        assert runner.sha256(folder / name) == digest, name
    tokenizer = AutoTokenizer.from_pretrained(folder, local_files_only=True)
    decoder = importlib.import_module('04_factchecker.inference.atomic_decoding')
    atomic = importlib.import_module('04_factchecker.inference.atomic_verifier')
    backend = decoder.ConstrainedAtomicBackend(None, tokenizer)

    accepted_paths = []
    def accepts(raw, request, *, split_blocked_tokens=True):
        callback = backend.generation_options(request)['prefix_allowed_tokens_fn']
        ids = Sequence([tokenizer.eos_token_id])
        splits = []
        for token in tokenizer.encode(raw, add_special_tokens=False):
            allowed = callback(0, ids)
            if token not in allowed:
                if not split_blocked_tokens:
                    return False
                # LMFE's free-text shortcut excludes some merged punctuation
                # tokens, e.g. .",. Check an alternative legal path for the SAME text.
                piece = tokenizer.decode([token])
                splits.append(piece)
                for char in piece:
                    encoded = tokenizer.encode(char, add_special_tokens=False)
                    assert len(encoded) == 1 and tokenizer.decode(encoded) == char
                    if encoded[0] not in callback(0, ids):
                        return False
                    ids.append(encoded[0])
            else:
                ids.append(token)
        assert tokenizer.decode(ids[1:]) == raw
        valid = tokenizer.eos_token_id in callback(0, ids)
        if valid:
            accepted_paths.append({'generated_tokens_including_eos': len(ids), 'split_tokens': splits})
        return valid

    original = ROOT / 'research-runs/colab-atomic-v7/20261016T024708Z-a57ee72a/reviewed-probe/predictions.jsonl'
    accepted = []
    for line in (original.read_text().splitlines() if '--assessment-only' not in sys.argv else []):
        row = json.loads(line)
        trace = next(e for e in reversed(row['result']['trace']) if e.get('validation_issue') is None)
        assert accepts(json.dumps(trace['output']), trace['messages']), row['example_id']
        accepted.append(row['example_id'])
    fixture = AssessmentRepairTests()
    part, raw = fixture.fixture()
    # The frozen decoder emits numeric after explanation, as specified by its schema.
    for observation in raw['observations']:
        observation['numeric'] = observation.pop('numeric')
    request = [{'role': 'system', 'content': atomic.ASSESS_PROMPT}, {'role': 'user', 'content': json.dumps({
        'claim': fixture.claim, 'part': part, 'context': fixture.proof})}]
    canonical = accepts(json.dumps(raw), request, split_blocked_tokens=False)
    assert accepts(json.dumps(raw), request), 'Complete multi-quantity assessment must be representable'
    assessment_path = accepted_paths[-1]
    assert assessment_path['generated_tokens_including_eos'] <= criteria['max_new_tokens']
    bad_quote = deepcopy(raw)
    bad_quote['observations'][0]['quotes'] = ['The audit evaluated 70 models on 30 datasets.']
    assert not accepts(json.dumps(bad_quote), request), 'Fabricated source quote admitted'
    bad_number = deepcopy(raw)
    bad_number['observations'][0]['numeric'][0]['right']['value'] = '70'
    assert not accepts(json.dumps(bad_number), request), 'Ungrounded operand admitted'
    long_prose = deepcopy(raw)
    long_prose['explanation'] = 'x' * 129
    assert not accepts(json.dumps(long_prose), request), 'Overlong explanation admitted'
    result = {'kind': 'offline_real_tokenizer_feasibility', 'model_inference': False,
        'criteria_sha256': runner.sha256(runner.CRITERIA),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'shared_tokenizer_files': baseline['model_metadata']['shared_tokenizer_files'],
        'decomposition_fixtures_accepted': accepted, 'synthetic_multi_quantity_assessment_accepted': True,
        'assessment_canonical_reencoding_accepted': canonical, 'assessment_legal_token_path': assessment_path,
        'fabricated_quote_ungrounded_number_and_long_prose_rejected': True,
        'decoder': decoder.DECODER,
        'note': 'LMFE may forbid a merged free-text punctuation token while admitting the same text '
                'with split tokens. This verifies a legal path, not model inference, label accuracy or human review.'}
    (ROOT / 'docs/atomic-verifier-v8-tokenizer-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
