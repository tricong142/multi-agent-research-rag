# Thay DUY NHAT cell assessment-smoke bang toan bo cell nay, trong session cu.
# Khong tang budget, khong sua prediction/gold, khong tu cho phep chay probe.
# Chua chay inference T4 cellfix2; test local khong dam bao 12/12 nhan.
import copy, hashlib, json, shutil, subprocess, uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from google.colab import files

smoke_passed = False
assert all(k in globals() for k in ('root','out','env','python','manifest','run')), 'Session cu phai con cac bien cua notebook.'
if '_cellfix2_parent' not in globals():
    _cellfix2_parent = dict(root=Path(root), out=Path(out), env=env.copy(), manifest=copy.deepcopy(manifest))
parent = _cellfix2_parent
criteria_rel = 'research_rag/evaluation/atomic_verifier_criteria_v8.json'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
old = json.loads((parent['root']/criteria_rel).read_text())
assert old['policy'] == 'atomic-verifier-constrained-v8-cellfix1', 'Cell nay dung sau cellfix1, khong dung cho source da sua thu cong.'
for name, digest in old['source_sha256'].items():
    assert sha(parent['root']/name) == digest, 'Source thay doi: ' + name
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
new_root = parent['root'].parent/('workspace-cellfix2-'+run_id)
new_out = parent['out'].parent/('output-cellfix2-'+run_id)
new_root.mkdir(exist_ok=False)
new_out.mkdir(exist_ok=False)
for name, item in parent['manifest'].items():
    relative = PurePosixPath(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    source, target = parent['root']/name, new_root/name
    assert sha(source) == item['sha256'] and source.stat().st_size == item['size'], name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

atomic_patch = r'''

POLICY = 'atomic-verifier-constrained-v8-cellfix2'
ASSESS_PROMPT += """

Serialization rules enforced by the decoder:
For atomic parts, coverage is exactly {"complete":false,"members":[],"quotes":[]}.
That field describes population closure, not whether an atomic fact is proved.
Put the evidence in observations[i].quotes. Every true/false observation MUST
have a nonempty evidence list and the required numeric checks. An unsupported
numeric association is unknown with numeric=null; it is never false merely
because the number was not reported. For several claimed quantities, a true
observation needs a check for EVERY quantity. Do not leave numeric=null when
the claim and the cited source provide a numerical comparison.
Same subject/metric/time/condition means scope_match=matched EVEN IF values or
polarity disagree. Different values are handled by truth and numeric, not by
scope_match. Unknown and contradiction are different decisions.

Example of direct negative evidence about the SAME subject:
claim: The survey used paper forms.
context: The survey did not use paper forms.
output: {"scope_match":"matched","coverage":{"complete":false,"members":[],"quotes":[]},"observations":[{"member":"survey","truth":"false","quotes":["The survey did not use paper forms."],"explanation":"Explicit denial of the same predicate.","numeric":null}],"missing_information":[],"explanation":"Same scope; explicit counterevidence."}

Example of a value comparison (no implicit unit conversion):
claim: Build took 9 minutes.
context: Build took 9 hours, not 9 minutes.
output: {"scope_match":"matched","coverage":{"complete":false,"members":[],"quotes":[]},"observations":[{"member":"Build","truth":"false","quotes":["Build took 9 hours, not 9 minutes."],"explanation":"Hours were reported, not minutes.","numeric":[{"kind":"value","source_quote":"Build took 9 hours, not 9 minutes.","left":{"value":"9","unit":"minutes","quote":"9 minutes"},"right":{"value":"9","unit":"hours","quote":"9 hours"}}]}],"missing_information":[],"explanation":"Same scope; explicitly denied duration."}

Example of a counterexample to ALL:
claim: All nozzles remained open.
context: Nozzle A remained open, but nozzle B was blocked.
output: {"scope_match":"matched","coverage":{"complete":false,"members":[],"quotes":[]},"observations":[{"member":"nozzle B","truth":"false","quotes":["Nozzle A remained open, but nozzle B was blocked."],"explanation":"One nozzle was blocked.","numeric":null}],"missing_information":[],"explanation":"One counterexample refutes ALL."}
These examples describe decision semantics only. Use the actual input's exact
evidence, numbers and units. Never copy example evidence into the answer.
"""
'''
decoder_patch = r'''

from copy import deepcopy
from .atomic_verifier import numeric_proof_required
import lmformatenforcer.jsonschemaparser as _js
# Pinned LMFE 0.11.3 does not serialize boolean const correctly internally.
# Keep standard JSON boolean values; no conversion or weakening in the validator.
if not getattr(_js.get_parser, '_atomic_bool_const_fix', False):
    def _bool_const_parser(state, schema, _previous=_js.get_parser):
        const = (schema.extras or {}).get('const') if schema is not None else None
        if type(const) is bool:
            return _js.StringParsingState(state, ['true' if const else 'false'], False, False)
        return _previous(state, schema)
    _bool_const_parser._atomic_bool_const_fix = True
    _js.get_parser = _bool_const_parser
DECODER.update(policy='atomic-schema-decoding-v5-cellfix2',
    conditional_numeric_truth=True, conditional_evidence=True,
    atomic_population_coverage='not_required', boolean_const_compat=True)
_cellfix1_schema = assessment_schema
def assessment_schema(claim, part, context):
    schema = deepcopy(_cellfix1_schema(claim, part, context))
    props = schema['properties']
    cov = props['coverage']['properties']
    if part['quantifier'] == 'atomic':
        props['coverage'] = obj({'complete':{'const':False},
            'members':array(cov['members']['items'], maximum=0),
            'quotes':array(cov['quotes']['items'], maximum=0)})
    else:
        incomplete = deepcopy(cov)
        incomplete['complete'] = {'const':False}
        complete = deepcopy(cov)
        complete['complete'] = {'const':True}
        complete['members']['minItems'] = 1
        complete['quotes']['minItems'] = 1
        props['coverage'] = {'anyOf':[obj(incomplete),obj(complete)]}
    original = props['observations']['items']
    numeric = original['properties']['numeric']
    choices = numeric.get('anyOf',[numeric])
    nonnull = [s for s in choices if s.get('type') != 'null']
    need_numeric = numeric_proof_required(part,[context])
    unknown = deepcopy(original)
    unknown['properties']['truth']['enum'] = ['unknown']
    unknown['properties']['numeric'] = {'type':'null'}
    branches = [unknown]
    for truth in ('true','false'):
        if need_numeric and not nonnull:
            continue  # No grounded operand available; unknown remains representable.
        variant = deepcopy(original)
        variant['properties']['truth']['enum'] = [truth]
        variant['properties']['quotes']['minItems'] = 1
        if need_numeric:
            allowed = deepcopy(nonnull)
            count = len(numeric_requirements(part['quote']))
            if truth == 'true' and count > 1:
                allowed = [s for s in allowed if s.get('type') == 'array']
                for item in allowed:
                    item['minItems'] = count
            variant['properties']['numeric'] = allowed[0] if len(allowed)==1 else {'anyOf':allowed}
        branches.append(variant)
    props['observations']['items'] = {'anyOf':branches}
    props['observations']['minItems'] = 1 if source_members(context) else 0
    return schema
'''
for relative, patch in (('04_factchecker/inference/atomic_verifier.py',atomic_patch),
                         ('04_factchecker/inference/atomic_decoding.py',decoder_patch)):
    path = new_root/relative
    path.write_text(path.read_text(encoding='utf-8')+patch, encoding='utf-8')

test_rel = 'research_rag/tests/test_atomic_smoke_cellfix2.py'
tests = r'''
from copy import deepcopy
import json, unittest
from research_rag.tests import test_atomic_assessment_v8 as h
from research_rag.tests.test_atomic_verifier import a,part,assessment,observation,numeric,operand
class Cellfix2Tests(unittest.TestCase):
    setUp=h.AssessmentTokenFilterTests.setUp
    accepts=h.AssessmentTokenFilterTests.accepts
    ordered=h.AssessmentTokenFilterTests.ordered
    def request(self,claim,p,proof):
        return [{'role':'system','content':a.ASSESS_PROMPT},{'role':'user','content':json.dumps({'claim':claim,'part':p,'context':proof})}]
    def fixture(self):
        claim,proof='Capacity was 9 liters.','Capacity was 9 liters.'
        p=part(claim,metric='Capacity')
        raw=assessment([observation('Capacity','true',proof,
            numeric('value',proof,operand('9','liters'),operand('9','liters')))])
        return raw,self.request(claim,p,proof)
    def test_true_numeric_requires_quote_and_check(self):
        raw,request=self.fixture()
        self.assertTrue(self.accepts(self.ordered(raw),request))
        raw['observations'][0]['quotes']=[]
        self.assertFalse(self.accepts(self.ordered(raw),request))
        raw,request=self.fixture();raw['observations'][0]['numeric']=None
        self.assertFalse(self.accepts(self.ordered(raw),request))
    def test_atomic_population_flag_is_false_not_empty_true(self):
        raw,request=self.fixture();raw['coverage']['complete']=True
        self.assertFalse(self.accepts(self.ordered(raw),request))
        raw['coverage']['complete']=False
        self.assertTrue(self.accepts(self.ordered(raw),request))
    def test_missing_numeric_source_allows_unknown_not_false(self):
        claim,proof='Capacity was 9 liters.','Capacity was not reported.'
        p=part(claim,metric='Capacity')
        raw=assessment([observation('Capacity','unknown',proof)],missing=['Capacity measurement.'])
        request=self.request(claim,p,proof)
        self.assertTrue(self.accepts(self.ordered(raw),request))
        raw['observations'][0]['truth']='false'
        self.assertFalse(self.accepts(self.ordered(raw),request))
    def test_qualitative_false_requires_evidence(self):
        claim,proof='The survey used paper forms.','The survey did not use paper forms.'
        p=part(claim,metric='used paper forms')
        raw=assessment([observation('survey','false',proof)])
        request=self.request(claim,p,proof)
        self.assertTrue(self.accepts(self.ordered(raw),request))
        self.assertEqual(a.assess_part(raw,p,proof)['assessed_label'],'contradict')
        raw['observations'][0]['quotes']=[]
        self.assertFalse(self.accepts(self.ordered(raw),request))
    def test_quantified_complete_needs_nonempty_population(self):
        claim,proof='All pumps remained operable.','One pump failed.'
        p=part(claim,quantifier='all',metric='operable')
        raw=assessment([observation('pump','false',proof)])
        request=self.request(claim,p,proof)
        self.assertTrue(self.accepts(self.ordered(raw),request))
        raw['coverage']['complete']=True
        self.assertFalse(self.accepts(self.ordered(raw),request))
        raw['coverage'].update(members=['pump'],quotes=[proof])
        self.assertTrue(self.accepts(self.ordered(raw),request))
'''
(new_root/test_rel).write_text(tests, encoding='utf-8')
new_env = parent['env'].copy()
new_env['PYTHONPATH'] = str(new_root)
metadata_code = "import importlib,json; a=importlib.import_module('04_factchecker.inference.atomic_verifier'); d=importlib.import_module('04_factchecker.inference.atomic_decoding'); print(json.dumps({'policy':a.POLICY,'decoder':d.DECODER,'prompts':{'decompose':a.DECOMPOSE_PROMPT,'assess':a.ASSESS_PROMPT}}))"
metadata = json.loads(subprocess.check_output([python,'-c',metadata_code],cwd=new_root,env=new_env,text=True))
criteria = copy.deepcopy(old)
contract = json.loads((new_root/'research_rag/evaluation'/old['contract_file']).read_text())
contract.update(version='atomic-contract-constrained-v8-cellfix2')
contract['assessment']['conditional_decoder'] = 'True/false require evidence and applicable numeric records. Without grounded numeric operands only unknown is representable. Atomic population coverage is false with empty ledger; evidence remains in observations. Quantified complete coverage requires nonempty members/quotes.'
contract_name = 'atomic_verifier_contract_v8_cellfix2.json'
contract_path = new_root/'research_rag/evaluation'/contract_name
contract_path.write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
criteria.update(version='atomic-verifier-constrained-v8-cellfix2',policy=metadata['policy'],
    structured_decoder=metadata['decoder'],contract_file=contract_name,contract_sha256=sha(contract_path),
    prompt_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in metadata['prompts'].items()})
criteria['source_sha256'] = {name:sha(new_root/name) for name in list(old['source_sha256'])+[test_rel]}
changed = {'version','policy','structured_decoder','contract_file','contract_sha256','prompt_sha256','source_sha256'}
assert all(criteria[k]==old[k] for k in old.keys()-changed), 'Model/data/budget changed unexpectedly.'
assert criteria['prompt_sha256']['decompose']==old['prompt_sha256']['decompose']
(new_root/criteria_rel).write_text(json.dumps(criteria,indent=2)+'\n',encoding='utf-8')
root, out, env, statuses = new_root, new_out, new_env, {}
manifest = {p.relative_to(root).as_posix():{'size':p.stat().st_size,'sha256':sha(p)}
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
(out/'input-manifest.json').write_text(json.dumps(manifest,indent=2))
(out/'cellfix2-provenance.json').write_text(json.dumps({'candidate':criteria['version'],
    'parent_criteria_sha256':sha(parent['root']/criteria_rel),'candidate_criteria_sha256':sha(root/criteria_rel),
    'previous_output':str(parent['out']),'model_data_budgets_unchanged':True},indent=2))
try:
    modules = [p[:-3].replace('/','.').replace('\\','.') for p in criteria['source_sha256']
               if p.startswith('research_rag/tests/') and p.endswith('.py')]
    run('regression-cellfix2',[python,'-m','unittest',*modules,'-v'],timeout=900)
    run('smoke-validate-only-cellfix2',[python,'-m','research_rag.evaluation.evaluate_atomic_verifier',
        '--output-dir',str(out/'unused'),'--assessment-smoke','--validate-only'])
    code = run('assessment-smoke',[python,'-u','-m','research_rag.evaluation.evaluate_atomic_verifier',
        '--output-dir',str(out/'assessment-smoke'),'--assessment-smoke','--online-model-downloads'],
        timeout=2520,required=False)
    path = out/'assessment-smoke/metrics.json'
    metrics = json.loads(path.read_text()) if path.exists() else {}
    print(json.dumps(metrics,indent=2))
    smoke_passed = code==0 and metrics.get('automated_gate_pass') is True
finally:
    bundle()
    files.download(str(out.with_suffix('.zip')))
if smoke_passed:
    print('SMOKE DAT. Gui ZIP moi de kiem provenance/replay truoc cac gate tiep theo.')
else:
    print('SMOKE CHUA DAT. Da luu ZIP moi; dung tai day, khong chay probe/full39. Khong coi cell ket thuc la gate da dat.')
