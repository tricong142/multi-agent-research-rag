# Thay cell assessment-smoke hien tai bang TOAN BO noi dung file nay.
# Dung trong session cellfix2 cu; khong doi model, budget, gold hay gate.
# Regression local khong phai ket qua inference Qwen/T4.
import copy, hashlib, json, shutil, subprocess, uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from google.colab import files

smoke_passed = False
assert all(k in globals() for k in ('root','out','env','python','manifest','run','bundle')), 'Can session cellfix2 cu.'
criteria_rel = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def _find_cellfix3_parent():
    expected='a31549bda8776f6a566689c59378e5c47092faf6000d4597ef7ab82fdafa197b'
    manifest_hash='01d110cddae3bbdb4a41569429c255359c14a87c2f30f8c633817900bf269533'
    current=dict(root=Path(root),out=Path(out),env=env.copy())
    states=[current]+[s for k in ('_cellfix3_parent','_cellfix2_parent','_v8_before_cellfix')
        if isinstance((s:=globals().get(k)),dict) and 'root' in s and 'out' in s]
    roots=[]
    def add_root(path):
        path=Path(path).resolve()
        if path not in roots: roots.append(path)
    for state in states: add_root(state['root'])
    anchors={Path(s['root']).resolve().parent for s in states}
    anchors.update(Path(s['out']).resolve().parent for s in states)
    if 'run_root' in globals(): anchors.add(Path(run_root).resolve())
    if Path('/content').is_dir(): anchors.update(Path('/content').glob('atomic-v8-*'))
    for base in sorted(anchors):
        if base.is_dir():
            for path in sorted(base.glob('workspace-cellfix2-*'),reverse=True): add_root(path)
    diagnostics=[]
    for candidate in roots:
        path=candidate/criteria_rel
        detail={'root':str(candidate)}
        diagnostics.append(detail)
        if not path.is_file():
            detail['error']='criteria file missing'
            continue
        try:
            digest=sha(path)
            detail['criteria_sha256']=digest
            if digest!=expected: continue
            outputs=[]
            if candidate.name.startswith('workspace-cellfix2-'):
                outputs.append(candidate.with_name(candidate.name.replace('workspace-cellfix2-','output-cellfix2-',1)))
            matching=[s for s in states if Path(s['root']).resolve()==candidate]
            outputs.extend(Path(s['out']) for s in matching)
            outputs.extend(sorted(candidate.parent.glob('output-cellfix2-*'),reverse=True))
            for output in dict.fromkeys(outputs):
                manifest_path=output/'input-manifest.json'
                if not manifest_path.is_file(): continue
                try:
                    data=json.loads(manifest_path.read_text())
                except (OSError,ValueError):
                    continue
                fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                if fingerprint!=manifest_hash: continue
                for name,item in data.items():
                    relative=PurePosixPath(name)
                    assert not relative.is_absolute() and '..' not in relative.parts and '\\' not in name
                    source=candidate/relative
                    if not source.is_file() or source.stat().st_size!=item['size'] or sha(source)!=item['sha256']:
                        raise ValueError('Input integrity mismatch: '+name)
                chosen_env=next((s['env'] for s in matching if isinstance(s.get('env'),dict)),env)
                return dict(root=candidate,out=output,env=chosen_env.copy(),manifest=data)
            detail['error']='No matching audited input-manifest.json'
        except (OSError,ValueError,KeyError,TypeError) as exc:
            detail['error']=str(exc)
    raise RuntimeError('Khong tim thay source cellfix2 da audit; chua chay smoke. '
        'Khong bo kiem hash. Root/hash tim thay: '+json.dumps(diagnostics,ensure_ascii=False))

# Cache only after criteria, manifest and all input bytes have been verified.
parent=_find_cellfix3_parent()
_cellfix3_parent=parent
print('Verified cellfix2 parent:',parent['root'])
old = json.loads((parent['root']/criteria_rel).read_text())
for name,digest in old['source_sha256'].items():
    assert sha(parent['root']/name)==digest, 'Source thay doi: '+name
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
new_root = parent['root'].parent/('workspace-cellfix3-'+run_id)
new_out = parent['out'].parent/('output-cellfix3-'+run_id)
new_root.mkdir(exist_ok=False)
new_out.mkdir(exist_ok=False)
for name,item in parent['manifest'].items():
    relative=PurePosixPath(name)
    assert not relative.is_absolute() and '..' not in relative.parts and '\\' not in name
    source,target=parent['root']/name,new_root/name
    assert sha(source)==item['sha256'] and source.stat().st_size==item['size'],name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)

"""Source deltas for an isolated cellfix3 candidate; released v8/cellfix2 stay intact."""

NUMERIC_PATCH = r'''

# Cellfix3: bind a record to its measurement clause before numerical comparison.
_cellfix2_numeric = check_numeric
_NUMERIC_MODAL = r'\b(?:hypothetical|would|could|may|might|should|if|expected|predicted|approximately|about)\b'

def measurement_clauses(proof):
    return [p.strip(' ,') for p in re.split(
        r';|[.!?](?=\s|$)|\b(?:and|but|whereas)\b', proof, flags=re.I
    ) if p.strip(' ,')]

def measurement_scope(raw, claim_part, metric):
    """Return an exact source clause and finite lexical binding, not entailment."""
    proof = raw['source_quote']
    if raw['kind'] != 'value':
        return proof, bool(metric and metric.casefold() in proof.casefold())
    left, right = raw['left'], raw['right']
    requirements = numeric_requirements(claim_part)
    anchor = left['unit'] if len(requirements) > 1 else metric
    if not anchor:
        return proof, True
    time_units = {'ms','s','second','seconds','minute','minutes','hour','hours'}
    lu, ru = left['unit'].casefold(), right['unit'].casefold()
    if len(requirements) > 1 and lu != ru and not {lu,ru} <= time_units:
        return proof, False
    families = (r'takes?|took', r'contains?|contained', r'uses?|used', r'evaluates?|evaluated')
    first = anchor.split()[0].casefold()
    family = next((f for f in families if re.fullmatch(f, first)), None)
    def matches(clause):
        positions = _occurrences(right['quote'], clause)
        if not positions or all(re.search(r'\b(?:not|never)\s*$',clause[:m.start()],re.I) for m in positions):
            return False
        if family:
            return bool(re.search(r'\b(?:'+family+r')\s+(?:exactly\s+)?'
                +re.escape(right['quote'])+r'(?!\w)', clause, re.I))
        return bool(re.search(r'(?<!\w)'+re.escape(anchor)+r'(?!\w)', clause, re.I))
    candidates = [c for c in measurement_clauses(proof) if matches(c)]
    if not candidates:
        return proof, False
    # Preserve shared modality and broad negation rather than strip a prefix.
    broad = r'\b(?:not true|not the case|not established|not known|no evidence|neither)\b'
    if (len(candidates) != 1 or re.search(_NUMERIC_MODAL+'|'+broad, proof, re.I)):
        return proof, True
    selected = candidates[0]
    prefix = proof[:proof.find(selected)]
    if re.search(r'\b(?:not|never|without)\b', prefix, re.I):
        return proof, True
    # A later denial can refer back to the selected statement. Only separate
    # an explicit different measurement; pronoun/back-reference scope is unknown.
    properties = {'accuracy','precision','recall','latency','memory','throughput',
        'capacity','duration','cost','speed','temperature','pressure','score'}
    own_words = set(re.findall(r'[a-z]+',anchor.casefold()))
    for other in measurement_clauses(proof):
        if other==selected or not re.search(r'\b(?:not|never|without)\b',other,re.I):
            continue
        words = set(re.findall(r'[a-z]+',other.casefold()))
        units = {r['unit'].casefold() for r in numeric_requirements(other)} - {'','%','percent'}
        if (not numeric_requirements(other) or own_words & words
                or words & {'this','it','that','claim','finding','above'}
                or not (properties & words - own_words or units - {lu,ru})):
            return proof, True
    verb = r'\b(?:is|was|were|uses?|used|retains?|retained|contains?|contained|takes?|took|evaluates?|evaluated|fell|rose|increased|decreased|improved|reduced|measured|recorded|reported|achieved|reached|scored|included|comprised|has|had)\b'
    return (selected if re.search(verb, selected, re.I) else proof), True

def check_numeric(raw, claim_part, context, *, metric=''):
    # The original checker validates all source spans, operands and claim guards.
    result = _cellfix2_numeric(raw, claim_part, context)
    if raw['kind'] != 'value':
        return result
    proof, bound = measurement_scope(raw, claim_part, metric)
    if metric and not bound:
        return {**result, 'truth':'unknown', 'reason':'numeric_metric_binding_unresolved'}
    if proof != raw['source_quote']:
        narrowed = {**raw, 'source_quote':proof}
        result = {**_cellfix2_numeric(narrowed, claim_part, context), 'input':raw}
    # Only extend the already-qualified explicit-denial grammar. Other claim
    # guards (thresholds, negated claim, unit grounding) retain their result.
    if result['reason'] != 'qualified_numeric_evidence' or re.search(_NUMERIC_MODAL, proof, re.I):
        return result
    left, lu, lq = _operand(raw['left'], claim_part)
    right, ru, rq = _operand(raw['right'], proof)
    if (left,lu) == (right,ru) or direction(claim_part) is not None:
        return result
    denial = re.search(r'(?<!\w)'+re.escape(rq)
        +r'(?P<bridge>(?:\s+[A-Za-z][A-Za-z-]*){0,4})\s*,?\s+(?:but\s+)?not\s+'
        +re.escape(lq)+r'(?!\w)', proof, re.I)
    if not denial:
        return result
    bridge = re.findall(r'[a-z-]+', denial['bridge'].casefold())
    claim_words = set(re.findall(r'[a-z-]+', claim_part.casefold()))
    remainder = proof[:denial.start()] + proof[denial.end():]
    if (any(w not in claim_words for w in bridge)
            or re.search(r'\b(?:not|never|without)\b', remainder, re.I)):
        return result
    return {**result, 'truth':'false', 'reason':'explicit_quantity_denial'}
'''

ATOMIC_PATCH = r'''

from .numeric_verifier import measurement_scope, measurement_clauses
POLICY = 'atomic-verifier-constrained-v8-cellfix3'

def target_entity(part):
    entity = re.sub(r'^(?:the|an)\s+', '', part['scope']['entity'].strip(), flags=re.I)
    if entity.casefold() in {'the','an','every','all','some','none'} or not entity:
        return ''
    return entity

def target_members(part, context):
    """Exact entity spans with optional leading article; no guessed aliases."""
    entity = target_entity(part)
    if not entity:
        return []
    return sorted({m[0] for m in re.finditer(r'(?<!\w)'+re.escape(entity)+r'(?!\w)', context, re.I)})

def other_named_target(part, proof):
    """Reject explicit sibling names; do not infer aliases or coreference."""
    words = target_entity(part).split()
    if len(words)<2:
        return False
    head, name = ' '.join(words[:-1]), words[-1].casefold()
    mentions = re.findall(r'(?<!\w)'+re.escape(head)+r'\s+([\w-]+)',proof,re.I)
    return bool(mentions) and name not in {m.casefold() for m in mentions}

def numeric_metric_matches(part, record, requirements):
    proof, bound = measurement_scope(record, part['quote'], part['scope']['metric'])
    return bound and not other_named_target(part,proof)

_cellfix2_assess = assess_part
def assess_part(raw, part, context):
    # Validate the complete original output first, including duplicate identities.
    result = _cellfix2_assess(raw, part, context)
    targets = target_members(part, context) if part['quantifier']=='atomic' else []
    if targets and any(o['member'] not in targets for o in result['observations']):
        raise ValueError('observation_target_mismatch')
    if targets and any(o['truth']!='unknown' and any(other_named_target(part,q) for q in o['quotes']) for o in result['observations']):
        raise ValueError('observation_target_mismatch')
    if targets and len(result['observations']) > 1:
        raise ValueError('atomic_target_observation_count')
    if part['quantifier']=='atomic' and target_entity(part) and not targets and result['assessed_label'] != 'not_enough_info':
        result = {**result,'assessed_label':'not_enough_info',
            'validation_issues':sorted(set(result['validation_issues']+['observation_target_unresolved'])),
            'explanation':'The exact target is absent; alias/coreference binding is unresolved.',
            'missing_information':result['missing_information'] or ['Evidence identifying the claimed target.']}
    if 'numeric_metric_binding_unresolved' in result['validation_issues']:
        # Retry only if context offers an alternative for the failed measurement.
        # An absent metric remains a valid unknown rather than a forced failure.
        requirements = numeric_requirements(part['quote'])
        for obs in result['observations']:
            records = obs['numeric'] if isinstance(obs['numeric'],list) else [obs['numeric']] if obs['numeric'] else []
            for record in records:
                if obs['model_truth']=='unknown' or numeric_metric_matches(part,record,requirements):
                    continue
                for clause in measurement_clauses(context):
                    for measured in numeric_requirements(clause):
                        candidate = {**record,'source_quote':clause,
                            'right':{k:measured[k] for k in ('value','unit','quote')}}
                        if numeric_metric_matches(part,candidate,requirements):
                            raise ValueError('numeric_metric_binding_unresolved')
    return result

REPAIR_HINTS.update(
    observation_identity_or_truth='Do not repeat member. Use one observation for the atomic target, with all relevant quotes/checks. Conflicting evidence is unknown, never silently discarded.',
    observation_target_mismatch='Use part.scope.entity as the observation target. Do not add baseline, metric or dataset as another member. Put evidence for all quantities in the target observation.',
    atomic_target_observation_count='Use one target observation with all relevant evidence. Preserve counterevidence; conflicting evidence is unknown.',
    numeric_metric_binding_unresolved='Bind each claimed quantity to evidence for the SAME metric/object. Different sentences can supply different records in the SAME observation. If that measurement is absent, use unknown/null.',
)
ASSESS_PROMPT += """

For an atomic part use ONE target observation. member is the exact context span
matching part.scope.entity when present. A baseline, measurement name or dataset
is not another target. Put multiple evidence sentences and one numeric check per
claimed quantity in this observation. Preserve conflicting evidence as unknown;
never choose one side merely to get a decisive answer.
Match each numeric right operand to its own metric/object and source sentence.
Two source sentences can jointly establish two quantities of the same event.
An explicit reported percentage reduction needs no unreported baseline value.
Negation belongs to the predicate it modifies. A denial of another metric does
not deny the current one. Explicit 'observed value + metric, not claimed value'
is counterevidence for that metric. Missing evidence remains unknown.
"""
'''

DECODER_PATCH = r'''

from .atomic_verifier import target_members, target_entity, numeric_metric_matches
DECODER.update(policy='atomic-schema-decoding-v5-cellfix3',
    target_observation_binding=True, per_requirement_source_binding=True,
    measurement_negation_scope=True)
_cellfix2_schema = assessment_schema

def assessment_schema(claim, part, context):
    schema = _cellfix2_schema(claim, part, context)
    props = schema['properties']
    targets = target_members(part, context) if part['quantifier']=='atomic' else []
    if targets:
        props['observations']['maxItems'] = 1
    choices = []
    for passage in evidence_passages(context):
        for left in operand_schema(part['quote']):
            lhs = {k:v['enum'][0] for k,v in left['properties'].items()}
            for right in operand_schema(passage):
                rhs = {k:v['enum'][0] for k,v in right['properties'].items()}
                record = dict(kind='value',source_quote=passage,left=lhs,right=rhs)
                if numeric_metric_matches(part,record,numeric_requirements(part['quote'])):
                    choices.append(obj({'kind':{'type':'string','enum':['value']},
                        'source_quote':{'type':'string','enum':[passage]},
                        'left':left,'right':right}))
    count = len(numeric_requirements(part['quote']))
    for branch in props['observations']['items']['anyOf']:
        obs = branch['properties']
        if targets:
            obs['member'] = {'type':'string','enum':targets}
        truth = obs['truth']['enum'][0]
        if count and truth != 'unknown':
            if not choices:
                branch['_remove'] = True
                continue
            record = choices[0] if len(choices)==1 else {'anyOf':choices}
            checks = array(record,minimum=count if truth=='true' else 1,maximum=count)
            obs['numeric'] = {'anyOf':[record,checks]} if count==1 else checks
    branches = [b for b in props['observations']['items']['anyOf'] if not b.pop('_remove',False)]
    if part['quantifier']=='atomic' and target_entity(part) and not targets:
        branches = [b for b in branches if b['properties']['truth']['enum']==['unknown']]
    props['observations']['items']['anyOf'] = branches
    return schema
'''


def apply_patch(root):
    """Apply only to a verified copied workspace. Return intentional fixture edit."""
    for name, patch in (
        ('04_factchecker/inference/numeric_verifier.py', NUMERIC_PATCH),
        ('04_factchecker/inference/atomic_verifier.py', ATOMIC_PATCH),
        ('04_factchecker/inference/atomic_decoding.py', DECODER_PATCH),
    ):
        path = root / name
        text = path.read_text(encoding='utf-8')
        if name.endswith('/atomic_verifier.py'):
            old = "value = check_numeric(record, part['quote'], context)"
            assert text.count(old) == 1
            text = text.replace(old,"value = check_numeric(record, part['quote'], context, metric=part['scope']['metric'])")
        path.write_bytes((text + patch).encode('utf-8'))
    # This old positive decoder fixture has A and B for atomic target A. The new
    # target contract rejects it; retain a positive single-target assertion.
    path = root / 'research_rag/tests/test_atomic_smoke_cellfix.py'
    text = path.read_text(encoding='utf-8')
    old = "raw=assessment([observation(m,'true',m+' improved.') for m in ('A','B')])\n        self.assertTrue(self.accepts(self.ordered(raw),self.request(claim,p,proof)))"
    new = old.replace('self.assertTrue','self.assertFalse') + "\n        raw['observations']=raw['observations'][:1]\n        self.assertTrue(self.accepts(self.ordered(raw),self.request(claim,p,proof)))"
    assert text.count(old) == 1
    path.write_bytes(text.replace(old,new).encode('utf-8'))
    # Wrong object binding with available correct evidence is now rejected into
    # repair, rather than accepted as a final NEI. This strengthens the old test.
    path = root / 'research_rag/tests/test_atomic_contract_v5.py'
    text = path.read_text(encoding='utf-8')
    old = "        self.assertEqual(self.assess(proof, swapped)['assessed_label'], 'not_enough_info')"
    new = "        with self.assertRaisesRegex(ValueError, 'numeric_metric_binding_unresolved'):\n            self.assess(proof, swapped)"
    assert text.count(old) == 1
    path.write_bytes(text.replace(old,new).encode('utf-8'))


TESTS = r'''
"""Cellfix3 development tests. Novel examples here are NOT held-out evaluation."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from research_rag.tests.test_atomic_verifier import (
    a, n, part, observation, assessment, operand, numeric, run
)
from research_rag.tests import test_atomic_assessment_v8 as h

def scoped(claim, entity, metric, **kwargs):
    p = part(claim, metric=metric, **kwargs)
    p['scope']['entity'] = entity
    return p

def request(claim,p,context):
    return [{'role':'system','content':a.ASSESS_PROMPT},
        {'role':'user','content':json.dumps({'claim':claim,'part':p,'context':context})}]

class BindingTests(unittest.TestCase):
    setUp=h.AssessmentTokenFilterTests.setUp
    accepts=h.AssessmentTokenFilterTests.accepts
    ordered=h.AssessmentTokenFilterTests.ordered

    def counts(self):
        claim='The audit evaluated six systems on three corpora.'
        first='Six systems were evaluated in the audit.'
        second='The evaluation used three corpora.'
        p=scoped(claim,'audit','evaluated six systems',condition='on three corpora')
        records=[numeric('value',first,operand('6','systems','six systems'),operand('6','systems','Six systems')),
            numeric('value',second,operand('3','corpora','three corpora'),operand('3','corpora','three corpora'))]
        raw=assessment([observation('audit','true',first,records)])
        raw['observations'][0]['quotes'].append(second)
        return claim,p,first+' '+second,raw

    def test_cross_sentence_quantities_share_one_target_observation(self):
        claim,p,proof,raw=self.counts()
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'support')
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,proof)))

    def test_wrong_object_binding_is_filtered_and_enters_bounded_repair(self):
        claim,p,proof,good=self.counts();bad=deepcopy(good)
        bad['observations'][0]['numeric'][1].update(
            source_quote=good['observations'][0]['numeric'][0]['source_quote'],
            right=operand('6','systems','Six systems'))
        self.assertFalse(self.accepts(self.ordered(bad),request(claim,p,proof)))
        with self.assertRaisesRegex(ValueError,'numeric_metric_binding_unresolved'):
            a.assess_part(bad,p,proof)
        result,backend=run([{'parts':[p],'unresolved':[]},bad,good],claim,proof)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(result['backend_calls'],3)
        self.assertIn('SAME metric/object',backend.calls[-1][0][-1]['content'])

    def test_absent_measurement_remains_unknown_without_forcing_repair(self):
        claim,p,proof,raw=self.counts()
        proof='Six systems were evaluated in the audit.'
        raw['observations'][0].update(truth='unknown',numeric=None,quotes=[proof])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'not_enough_info')
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,proof)))

    def test_true_requires_every_quantity_and_repeated_requirement_is_rejected(self):
        claim,p,proof,raw=self.counts();raw['observations'][0]['numeric'].pop()
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,proof)))
        with self.assertRaisesRegex(ValueError,'numeric_requirement_missing'):
            a.assess_part(raw,p,proof)
        raw['observations'][0]['numeric'] *= 2
        with self.assertRaisesRegex(ValueError,'duplicate_numeric_requirement'):
            a.assess_part(raw,p,proof)

    def test_atomic_target_rejects_baseline_and_duplicate_without_discarding_it(self):
        claim='Model Larch retained accuracy.'
        proof='Model Larch retained accuracy. The baseline was unmeasured.'
        p=scoped(claim,'Model Larch','accuracy')
        good=assessment([observation('Model Larch','true','Model Larch retained accuracy.')])
        bad=deepcopy(good)
        bad['observations'].append(observation('baseline','unknown','The baseline was unmeasured.'))
        with self.assertRaisesRegex(ValueError,'observation_target_mismatch'):
            a.assess_part(bad,p,proof)
        self.assertFalse(self.accepts(self.ordered(bad),request(claim,p,proof)))
        self.assertTrue(self.accepts(self.ordered(good),request(claim,p,proof)))
        bad=deepcopy(good);bad['observations'] *= 2
        with self.assertRaisesRegex(ValueError,'observation_identity_or_truth'):
            a.assess_part(bad,p,proof)

    def test_target_error_repair_preserves_budget(self):
        claim='Model Larch retained accuracy.';proof=claim+' The baseline was unmeasured.'
        p=scoped(claim,'Model Larch','accuracy')
        good=assessment([observation('Model Larch','true',claim)])
        bad=assessment([observation('baseline','unknown','The baseline was unmeasured.')])
        result,backend=run([{'parts':[p],'unresolved':[]},bad,good],claim,proof)
        self.assertEqual(result['assessed_label'],'support')
        self.assertEqual(result['backend_calls'],3)
        self.assertEqual(result['trace'][1]['validation_issue'],'observation_target_mismatch')
        exhausted,_=run([{'parts':[p],'unresolved':[]},bad,bad],claim,proof)
        self.assertEqual(exhausted['stop_reason'],'invalid_output_exhausted')
        self.assertIsNone(exhausted['assessed_label'])

    def test_missing_target_never_becomes_support(self):
        claim='Model Larch retained accuracy.';proof='Model Cedar retained accuracy.'
        p=scoped(claim,'Model Larch','accuracy')
        raw=assessment([observation('Model Cedar','true',proof)])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'not_enough_info')
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,proof)))
        raw['observations'][0]['truth']='unknown'
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,proof)))

    def test_correct_member_cannot_borrow_another_named_targets_measurement(self):
        claim='Model Larch retained 71% accuracy.'
        first='Model Larch was tested.';second='Model Cedar retained 71% accuracy.'
        proof=first+' '+second;p=scoped(claim,'Model Larch','accuracy')
        for citation in (second,proof):
            check=numeric('value',citation,operand('71','%','71%'),operand('71','%','71%'))
            raw=assessment([observation('Model Larch','true',proof,[check])])
            self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'not_enough_info')
            self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,proof)))

    def test_conflicting_quotes_declared_unknown_are_not_promoted(self):
        claim='Accuracy was 71%.';proof='Accuracy was 71%. Accuracy was 63%.'
        p=scoped(claim,'Accuracy','Accuracy')
        raw=assessment([observation('Accuracy','unknown',proof)])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'not_enough_info')
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,proof)))

    def test_metric_bridge_in_explicit_denial(self):
        claim='Model Aspen retained 71% accuracy.'
        proof='Model Aspen retained 63% accuracy, not 71%.'
        p=scoped(claim,'Model Aspen','accuracy')
        check=numeric('value',proof,operand('71','%','71%'),operand('63','%','63%'))
        raw=assessment([observation('Model Aspen','false',proof,[check])])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'contradict')
        self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,proof)))
        for prefix in ('If measured, ','Hypothetically, the model might: '):
            source=prefix+proof
            changed=deepcopy(check);changed['source_quote']=source
            self.assertEqual(n.check_numeric(changed,claim,source,metric='accuracy')['truth'],'unknown')

    def test_denied_quantity_is_not_the_observed_right_operand(self):
        claim='Model Aspen retained 71% accuracy.'
        proof='Model Aspen retained 63% accuracy, not 71%.'
        p=scoped(claim,'Model Aspen','accuracy')
        check=numeric('value',proof,operand('71','%','71%'),operand('71','%','71%'))
        raw=assessment([observation('Model Aspen','true',proof,[check])])
        self.assertFalse(self.accepts(self.ordered(raw),request(claim,p,proof)))
        with self.assertRaisesRegex(ValueError,'numeric_metric_binding_unresolved'):
            a.assess_part(raw,p,proof)

    def test_other_metric_denial_does_not_poison_positive_memory(self):
        claim='Model Aspen used 18% less memory.'
        proof='Model Aspen used 18% less memory and retained 79% accuracy, not 92%.'
        p=scoped(claim,'Model Aspen','memory')
        check=numeric('value',proof,operand('18','%','18%'),operand('18','%','18%'))
        raw=assessment([observation('Model Aspen','true',proof,[check])])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'support')
        wrong=deepcopy(check);wrong['right']=operand('79','%','79%')
        self.assertFalse(a.numeric_metric_matches(p,wrong,n.numeric_requirements(claim)))

    def test_measurement_scope_generalizes_to_other_properties_and_units(self):
        claim='Pump Delta recorded 18 bar pressure.'
        proof='Pump Delta recorded 18 bar pressure and reported 25 C temperature, not 30 C.'
        p=scoped(claim,'Pump Delta','pressure')
        check=numeric('value',proof,operand('18','bar'),operand('18','bar'))
        raw=assessment([observation('Pump Delta','true',proof,[check])])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'support')
        claim='Cost was 37 dollars.'
        proof='Cost was 37 dollars and latency was 5 seconds, not 8 seconds.'
        p=scoped(claim,'Cost','Cost')
        check=numeric('value',proof,operand('37','dollars'),operand('37','dollars'))
        raw=assessment([observation('Cost','true',proof,[check])])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'support')

    def test_shared_modality_and_broad_negation_are_preserved(self):
        claim='Accuracy was 91%.'
        for proof in ('If measured, memory was 18% and accuracy was 91%.',
                'It is not true that memory was 18% and accuracy was 91%.',
                'Memory was not 18% and accuracy 91%.'):
            check=numeric('value',proof,operand('91','%','91%'),operand('91','%','91%'))
            self.assertEqual(n.check_numeric(check,claim,proof,metric='accuracy')['truth'],'unknown')

    def test_back_reference_and_preceding_negation_cannot_be_stripped(self):
        claim='Accuracy was 91%.'
        for proof in ('Accuracy was 91% and this is not true.',
                'The team did not report memory was 18% and accuracy was 91%.',
                'It never happened that memory was 18% and accuracy was 91%.',
                'Accuracy was 91% and we did not confirm this with precision 63%.'):
            check=numeric('value',proof,operand('91','%','91%'),operand('91','%','91%'))
            self.assertEqual(n.check_numeric(check,claim,proof,metric='Accuracy')['truth'],'unknown')

    def test_threshold_claim_guard_is_not_overridden(self):
        proof='Accuracy was 63% accuracy, not 71%.'
        check=numeric('value',proof,operand('71','%','71%'),operand('63','%','63%'))
        for claim in ('Accuracy was at least 71%.','Accuracy was not 71%.'):
            self.assertEqual(n.check_numeric(check,claim,proof,metric='Accuracy')['truth'],'unknown')

    def test_named_properties_and_quantifiers_keep_their_contract(self):
        for prop in ('accuracy','latency'):
            claim='The service improved '+prop+'.';p=scoped(claim,'service',prop)
            raw=assessment([observation('service','true',claim)])
            self.assertEqual(a.assess_part(raw,p,claim)['assessed_label'],'support')
            self.assertTrue(self.accepts(self.ordered(raw),request(claim,p,claim)))
        proof='Pump A improved. Pump B worsened.'
        claim='All pumps improved.';p=scoped(claim,'pumps','improved',quantifier='all')
        raw=assessment([observation('Pump B','false','Pump B worsened.')])
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'contradict')

    def test_real_cellfix2_invalid_targets_are_filtered(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/atomic_cellfix2_binding_traces.json').read_text())
        for case in fixture:
            with self.subTest(case=case['example_id'],stage=case['stage']):
                self.assertFalse(self.accepts(self.ordered(case['output']),request(case['claim'],case['part'],case['context'])))
'''

TRACE_FIXTURE = [{'example_id': 'contract:partial_memory', 'stage': 'part_1', 'claim': 'Model Juniper uses 25% less memory and retains 94% accuracy.', 'part': {'quote': 'Model Juniper uses 25% less memory', 'quantifier': 'atomic', 'scope': {'entity': 'Model Juniper', 'metric': 'memory', 'time': '', 'condition': ''}, 'start': 0, 'end': 34, 'numeric_requirements': [{'start': 19, 'end': 22, 'quote': '25%', 'value': '25', 'unit': '%', 'kind': 'percent'}]}, 'context': 'Model Juniper retains 94% accuracy on the benchmark.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'Model Juniper', 'truth': 'true', 'quotes': ['Model Juniper retains 94% accuracy on the benchmark.'], 'explanation': 'Same subject (Model Juniper) and metric (accuracy).', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper retains 94% accuracy on the benchmark.', 'left': {'value': '25', 'unit': '%', 'quote': '25%'}, 'right': {'value': '94', 'unit': '%', 'quote': '94%'}}]}, {'member': 'Model Juniper', 'truth': 'false', 'quotes': ['Model Juniper retains 94% accuracy on the benchmark.'], 'explanation': 'Accuracy is explicitly stated, not memory usage change', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper retains 94% accuracy on the benchmark.', 'left': {'value': '25', 'unit': '%', 'quote': '25%'}, 'right': {'value': '94', 'unit': '%', 'quote': '94%'}}]}], 'missing_information': [], 'explanation': 'Accuracy is explicitly stated, not memory usage change'}}, {'example_id': 'contract:partial_memory', 'stage': 'part_1', 'claim': 'Model Juniper uses 25% less memory and retains 94% accuracy.', 'part': {'quote': 'Model Juniper uses 25% less memory', 'quantifier': 'atomic', 'scope': {'entity': 'Model Juniper', 'metric': 'memory', 'time': '', 'condition': ''}, 'start': 0, 'end': 34, 'numeric_requirements': [{'start': 19, 'end': 22, 'quote': '25%', 'value': '25', 'unit': '%', 'kind': 'percent'}]}, 'context': 'Model Juniper retains 94% accuracy on the benchmark.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'Model Juniper', 'truth': 'true', 'quotes': ['Model Juniper retains 94% accuracy on the benchmark.'], 'explanation': 'Same scope; retention accuracy is unaffected by memory usage', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper retains 94% accuracy on the benchmark.', 'left': {'value': '25', 'unit': '%', 'quote': '25%'}, 'right': {'value': '94', 'unit': '%', 'quote': '94%'}}]}, {'member': 'Model Juniper', 'truth': 'false', 'quotes': ['Model Juniper retains 94% accuracy on the benchmark.'], 'explanation': 'Retention accuracy is unaffected by memory usage', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper retains 94% accuracy on the benchmark.', 'left': {'value': '25', 'unit': '%', 'quote': '25%'}, 'right': {'value': '94', 'unit': '%', 'quote': '94%'}}]}], 'missing_information': [], 'explanation': 'Observation confirms retention accuracy while denying memory use'}}, {'example_id': 'contract:both_supported', 'stage': 'part_1', 'claim': 'Model Juniper uses 25% less memory and retains 94% accuracy.', 'part': {'quote': 'Model Juniper uses 25% less memory', 'quantifier': 'atomic', 'scope': {'entity': 'Model Juniper', 'metric': 'memory', 'time': '', 'condition': ''}, 'start': 0, 'end': 34, 'numeric_requirements': [{'start': 19, 'end': 22, 'quote': '25%', 'value': '25', 'unit': '%', 'kind': 'percent'}]}, 'context': 'Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'Model Juniper', 'truth': 'true', 'quotes': ['Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.'], 'explanation': 'Same scope; explicitly stated memory usage reduction', 'numeric': [{'kind': 'value', 'source_quote': 'Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.', 'left': {'value': '25', 'unit': '%', 'quote': '25%'}, 'right': {'value': '25', 'unit': '%', 'quote': '25%'}}]}, {'member': 'baseline', 'truth': 'unknown', 'quotes': ['Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.'], 'explanation': 'Memory retention accuracy provided but not quantified', 'numeric': None}], 'missing_information': [], 'explanation': "Scope match; memory usage reduction confirmed, but baseline's %s"}}, {'example_id': 'contract:both_supported', 'stage': 'part_2', 'claim': 'Model Juniper uses 25% less memory and retains 94% accuracy.', 'part': {'quote': 'and retains 94% accuracy.', 'quantifier': 'atomic', 'scope': {'entity': 'Model Juniper', 'metric': 'accuracy', 'time': '', 'condition': ''}, 'start': 35, 'end': 60, 'numeric_requirements': [{'start': 12, 'end': 15, 'quote': '94%', 'value': '94', 'unit': '%', 'kind': 'percent'}]}, 'context': 'Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'Model Juniper', 'truth': 'true', 'quotes': ['Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.'], 'explanation': "Context confirms the model's accuracy", 'numeric': [{'kind': 'value', 'source_quote': 'Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.', 'left': {'value': '94', 'unit': '%', 'quote': '94%'}, 'right': {'value': '94', 'unit': '%', 'quote': '94%'}}]}, {'member': 'baseline', 'truth': 'unknown', 'quotes': ['Compared with the baseline, Model Juniper uses 25% less memory and retains 94% accuracy.'], 'explanation': "Accuracy is confirmed, but baseline's memory usage is not stated", 'numeric': None}], 'missing_information': [], 'explanation': "Context confirms the model's accuracy, but baseline's memory is "}}, {'example_id': 'contract:accuracy_conflict', 'stage': 'part_1', 'claim': 'Model Juniper uses 25% less memory and retains 94% accuracy.', 'part': {'quote': 'Model Juniper uses 25% less memory', 'quantifier': 'atomic', 'scope': {'entity': 'Model Juniper', 'metric': 'memory', 'time': '', 'condition': ''}, 'start': 0, 'end': 34, 'numeric_requirements': [{'start': 19, 'end': 22, 'quote': '25%', 'value': '25', 'unit': '%', 'kind': 'percent'}]}, 'context': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'accuracy', 'truth': 'false', 'quotes': ['Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.'], 'explanation': 'Accuracy was explicitly stated as 81%, not 94%', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'left': {'value': '25', 'unit': '%', 'quote': '25%'}, 'right': {'value': '81', 'unit': '%', 'quote': '81%'}}]}, {'member': 'memory', 'truth': 'true', 'quotes': ['Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.'], 'explanation': 'Memory was explicitly stated as 25% less', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'left': {'value': '25', 'unit': '%', 'quote': '25%'}, 'right': {'value': '25', 'unit': '%', 'quote': '25%'}}]}], 'missing_information': [], 'explanation': 'Scope match; accuracy explicitly contradicted while memory is as'}}, {'example_id': 'contract:accuracy_conflict', 'stage': 'part_2', 'claim': 'Model Juniper uses 25% less memory and retains 94% accuracy.', 'part': {'quote': 'and retains 94% accuracy.', 'quantifier': 'atomic', 'scope': {'entity': 'Model Juniper', 'metric': 'accuracy', 'time': '', 'condition': ''}, 'start': 35, 'end': 60, 'numeric_requirements': [{'start': 12, 'end': 15, 'quote': '94%', 'value': '94', 'unit': '%', 'kind': 'percent'}]}, 'context': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'Model Juniper', 'truth': 'false', 'quotes': ['Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.'], 'explanation': 'Accuracy is explicitly lower than claimed', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'left': {'value': '94', 'unit': '%', 'quote': '94%'}, 'right': {'value': '81', 'unit': '%', 'quote': '81%'}}]}, {'member': 'Model Juniper', 'truth': 'false', 'quotes': ['Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.'], 'explanation': 'Accuracy is explicitly lower than claimed', 'numeric': [{'kind': 'value', 'source_quote': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'left': {'value': '94', 'unit': '%', 'quote': '94%'}, 'right': {'value': '81', 'unit': '%', 'quote': '81%'}}]}], 'missing_information': [], 'explanation': 'Accuracy explicitly contradicted with lower value'}}, {'example_id': 'contract:accuracy_conflict', 'stage': 'part_2', 'claim': 'Model Juniper uses 25% less memory and retains 94% accuracy.', 'part': {'quote': 'and retains 94% accuracy.', 'quantifier': 'atomic', 'scope': {'entity': 'Model Juniper', 'metric': 'accuracy', 'time': '', 'condition': ''}, 'start': 35, 'end': 60, 'numeric_requirements': [{'start': 12, 'end': 15, 'quote': '94%', 'value': '94', 'unit': '%', 'kind': 'percent'}]}, 'context': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'Model Juniper', 'truth': 'false', 'quotes': ['Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.'], 'explanation': 'Accuracy is explicitly lower than claimed', 'numeric': {'kind': 'value', 'source_quote': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'left': {'value': '94', 'unit': '%', 'quote': '94%'}, 'right': {'value': '81', 'unit': '%', 'quote': '81%'}}}, {'member': 'Model Juniper', 'truth': 'false', 'quotes': ['Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.'], 'explanation': 'Accuracy is explicitly lower than claimed', 'numeric': {'kind': 'value', 'source_quote': 'Model Juniper uses 25% less memory and retains 81% accuracy, not 94%.', 'left': {'value': '94', 'unit': '%', 'quote': '94%'}, 'right': {'value': '81', 'unit': '%', 'quote': '81%'}}}], 'missing_information': [], 'explanation': 'Accuracy explicitly contradicted with lower value'}}, {'example_id': 'contract:cross_sentence', 'stage': 'part_1', 'claim': 'The report evaluated four models on two datasets.', 'part': {'quote': 'The report evaluated four models on two datasets.', 'quantifier': 'atomic', 'scope': {'entity': 'report', 'metric': 'evaluated four models', 'time': '', 'condition': 'on two datasets'}, 'start': 0, 'end': 49, 'numeric_requirements': [{'start': 21, 'end': 32, 'quote': 'four models', 'value': '4', 'unit': 'models', 'kind': 'number'}, {'start': 36, 'end': 48, 'quote': 'two datasets', 'value': '2', 'unit': 'datasets', 'kind': 'number'}]}, 'context': 'Four models were evaluated in the report. Evaluation used two datasets.', 'output': {'scope_match': 'matched', 'coverage': {'complete': False, 'members': [], 'quotes': []}, 'observations': [{'member': 'Four models', 'truth': 'true', 'quotes': ['Four models were evaluated in the report.'], 'explanation': 'Positive evidence matches the claim', 'numeric': [{'kind': 'value', 'source_quote': 'Four models were evaluated in the report.', 'left': {'value': '4', 'unit': 'models', 'quote': 'four models'}, 'right': {'value': '4', 'unit': 'models', 'quote': 'Four models'}}, {'kind': 'value', 'source_quote': 'Four models were evaluated in the report.', 'left': {'value': '2', 'unit': 'datasets', 'quote': 'two datasets'}, 'right': {'value': '4', 'unit': 'models', 'quote': 'Four models'}}]}, {'member': 'two datasets', 'truth': 'unknown', 'quotes': ['Evaluation used two datasets.'], 'explanation': 'Evaluation used two datasets, but does not specify which models', 'numeric': None}], 'missing_information': [], 'explanation': 'Scope match but missing information about which models were used'}}]

apply_patch(new_root)
test_rel='research_rag/tests/test_atomic_smoke_cellfix3.py'
fixture_rel='research_rag/tests/fixtures/atomic_cellfix2_binding_traces.json'
(new_root/test_rel).write_bytes(TESTS.encode('utf-8'))
(new_root/fixture_rel).write_bytes((json.dumps(TRACE_FIXTURE,indent=2)+'\n').encode('utf-8'))
new_env=parent['env'].copy()
new_env['PYTHONPATH']=str(new_root)
metadata_code="import importlib,json;a=importlib.import_module('04_factchecker.inference.atomic_verifier');d=importlib.import_module('04_factchecker.inference.atomic_decoding');print(json.dumps({'policy':a.POLICY,'decoder':d.DECODER,'prompts':{'decompose':a.DECOMPOSE_PROMPT,'assess':a.ASSESS_PROMPT}}))"
metadata=json.loads(subprocess.check_output([python,'-c',metadata_code],cwd=new_root,env=new_env,text=True))
criteria=copy.deepcopy(old)
contract=json.loads((new_root/'research_rag/evaluation'/old['contract_file']).read_text())
contract.update(version='atomic-contract-constrained-v8-cellfix3')
contract['assessment']['target_binding']='One observation for an exactly source-matched atomic target, carrying all its evidence/checks. Out-of-target observations enter bounded repair; absent exact target cannot establish a decisive atomic label. Alias/coreference entailment is not inferred.'
contract['numeric']['measurement_binding']='Shared finite entity/metric/object binding for decoder and validator. Correct alternative measurement in context makes malformed binding repairable; an absent measurement remains unknown. Scope a value check to an exact independent measurement clause, retaining shared modality/broad negation. Explicit quantity denial allows a short claim-grounded metric noun bridge.'
contract_name='atomic_verifier_contract_v8_cellfix3.json'
contract_path=new_root/'research_rag/evaluation'/contract_name
contract_path.write_bytes((json.dumps(contract,indent=2)+'\n').encode('utf-8'))
criteria.update(version='atomic-verifier-constrained-v8-cellfix3',policy=metadata['policy'],
    structured_decoder=metadata['decoder'],contract_file=contract_name,contract_sha256=sha(contract_path),
    prompt_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in metadata['prompts'].items()})
criteria['source_sha256']={name:sha(new_root/name) for name in list(old['source_sha256'])+[test_rel,fixture_rel]}
criteria['limitations']=old['limitations']+['Cellfix3 exact-span target and finite English measurement-clause grammar are conservative. Aliases, semantic coreference, evidence completeness and unsupported syntax still require independent evaluation and review. No new model quality or full39 result is established by regression.']
changed={'version','policy','structured_decoder','contract_file','contract_sha256','prompt_sha256','source_sha256','limitations'}
assert all(criteria[k]==old[k] for k in old.keys()-changed), 'Model/data/budget/gate changed unexpectedly.'
assert criteria['prompt_sha256']['decompose']==old['prompt_sha256']['decompose']
(new_root/criteria_rel).write_bytes((json.dumps(criteria,indent=2)+'\n').encode('utf-8'))
root,out,env,statuses=new_root,new_out,new_env,{}
manifest={p.relative_to(root).as_posix():{'size':p.stat().st_size,'sha256':sha(p)}
    for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
(out/'input-manifest.json').write_text(json.dumps(manifest,indent=2))
(out/'cellfix3-provenance.json').write_text(json.dumps({'candidate':criteria['version'],
    'parent_criteria_sha256':sha(parent['root']/criteria_rel),'candidate_criteria_sha256':sha(root/criteria_rel),
    'previous_output':str(parent['out']),'model_data_budgets_and_gates_unchanged':True,
    'intentional_legacy_fixture_updates':['Two different members are no longer a valid atomic target decoder example; add a single-target positive assertion.','Wrong object binding with available correct evidence must reject into bounded repair rather than silently finalize NEI.']},indent=2))
(out/'cellfix3-patch-contents.json').write_text(json.dumps({'numeric_patch':NUMERIC_PATCH,
    'atomic_patch':ATOMIC_PATCH,'decoder_patch':DECODER_PATCH,'regression_tests':TESTS,
    'development_trace_fixture':TRACE_FIXTURE},indent=2))
try:
    modules=[p[:-3].replace('/','.').replace('\\','.') for p in criteria['source_sha256']
        if p.startswith('research_rag/tests/') and p.endswith('.py')]
    run('regression-cellfix3',[python,'-m','unittest',*modules,'-v'],timeout=900)
    for name,flag in (('probe-validate-only-cellfix3','--decomposition-probe'),
            ('smoke-validate-only-cellfix3','--assessment-smoke'),('verifier-validate-only-cellfix3',None)):
        command=[python,'-m','research_rag.evaluation.evaluate_atomic_verifier',
            '--output-dir',str(out/'unused'),'--validate-only']
        if flag: command.append(flag)
        run(name,command)
    run('cuda-preflight-cellfix3',[python,'-c',"import json,torch; assert torch.cuda.is_available(); print(json.dumps({'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__}))"])
    code=run('assessment-smoke',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
        '--output-dir',str(out/'assessment-smoke'),'--assessment-smoke','--online-model-downloads'],
        timeout=2520,required=False)
    path=out/'assessment-smoke/metrics.json'
    metrics=json.loads(path.read_text()) if path.exists() else {}
    print(json.dumps(metrics,indent=2))
    smoke_passed=code==0 and metrics.get('automated_gate_pass') is True
finally:
    bundle()
    files.download(str(out.with_suffix('.zip')))
if smoke_passed:
    print('SMOKE DAT. Gui ZIP moi de audit; probe18/human review/full39 van la cac gate tiep theo.')
else:
    print('SMOKE CHUA DAT. Da luu ZIP moi. Dung tai day; khong chay probe/full39.')
