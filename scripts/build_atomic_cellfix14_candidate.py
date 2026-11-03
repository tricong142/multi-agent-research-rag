"""Build an isolated successor; released cf13 bytes and gold remain unchanged."""
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'research-runs/atomic-cellfix14-candidate/workspace'
CRITERIA='research_rag/evaluation/atomic_verifier_criteria_v8.json'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def replace(text,before,after):
    if text.count(before)!=1:raise ValueError('Patch anchor changed: '+before[:100])
    return text.replace(before,after,1)


def replace_function(text,name,body):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=text.splitlines(keepends=True)
    return ''.join(lines[:node.lineno-1])+body+'\n'+''.join(lines[node.end_lineno:])


def patch_source():
    folder=SOURCE/'04_factchecker/inference'
    for short in ('quantities','binding_rules','runtime','decomposition','generation'):
        (folder/('cellfix14_'+short+'.py')).write_bytes((ROOT/'scripts'/('atomic_cellfix14_'+short+'.py')).read_bytes())
    path=folder/'numeric_verifier.py';text=path.read_text(encoding='utf-8')
    text=replace_function(text,'numeric_requirements','from .cellfix14_quantities import numeric_requirements')
    text=replace(text,'    if left_unit != right_unit:',
        "    from .cellfix14_quantities import compatible_count_units\n    if left_unit != right_unit and not (kind=='value' and compatible_count_units(left_unit,right_unit)):")
    text=replace(text,"    if len(requirements) > 1 and lu != ru and not {lu,ru} <= time_units:",
        "    from .cellfix14_quantities import compatible_count_units\n    if len(requirements) > 1 and lu != ru and not {lu,ru} <= time_units and not compatible_count_units(lu,ru):")
    text=replace(text,"        return bool(re.search(r'(?<!\\w)'+re.escape(anchor)+r'(?!\\w)', clause, re.I))",
        "        return bool(re.search(r'(?<!\\w)'+re.escape(anchor)+r'(?!\\w)', clause, re.I)) or compatible_count_units(anchor,right['unit'])")
    text=replace(text,'def _operand(raw: dict, source: str) -> tuple[Decimal, str, str]:',
        'def _original_operand(raw: dict, source: str) -> tuple[Decimal, str, str]:')
    text=replace(text,"        if len(requirements) <= 1 and quantities(claim_part, claim=True) != quantities(left_quote):",
        "        if len(requirements) <= 1 and {(Decimal(r['value']),r['kind']) for r in requirements} != quantities(left_quote):")
    text += '\n\nfrom .cellfix14_quantities import grounded_operand\ndef _operand(raw,source):\n    return grounded_operand(raw,source,_original_operand)\n'
    path.write_text(text,encoding='utf-8')
    path=folder/'atomic_verifier.py';text=path.read_text(encoding='utf-8')
    text=replace_function(text,'target_members',
        'def target_members(part,context):\n    from .cellfix14_binding_rules import source_targets\n    return source_targets(part,context)')
    text=replace(text,'    words = target_entity(part).split()',
        '    from .cellfix14_binding_rules import explicit_reference\n    if explicit_reference(part,proof):return False\n    words = target_entity(part).split()')
    text=replace(text,"    boundaries = [0] + [m.start() for m in re.finditer(r'\\band\\b', claim, re.I)] + [len(claim)]",
        "    from .cellfix14_decomposition import conjunctions\n    boundaries = [0] + [m.start() for m in conjunctions(claim)] + [len(claim)]")
    text=replace(text,"        if re.search(r'\\band\\b', predicate, re.I):",
        "        from .cellfix14_decomposition import conjunctions\n        if conjunctions(predicate):")
    text=replace(text,"        expected = inherited if own == 'atomic' else own",
        "        from .cellfix14_decomposition import expected_quantifier\n        expected = expected_quantifier(claim,part['quote'],_quantifier)")
    text=replace(text,"        if not raw['unresolved']:\n            issues = scope_issues(scope, claim, part['quote'])",
        "        if not raw['unresolved']:\n            from .cellfix14_decomposition import subject_issue\n            issue=subject_issue(scope,part['quote'])\n            if issue:raise ValueError(issue)\n            issues = scope_issues(scope, claim, part['quote'])")
    text += "\n\nPOLICY='atomic-verifier-constrained-v8-cellfix14'\nDECOMPOSE_PROMPT += '\\nKeep the grammatical subject separate from the comparator after than. Split factual predicates, not AND joining noun objects or purposes. Preserve all quantities and full compound objects; model/section identifiers are references. Quantifiers apply to their own predicate, not every part of the sentence. Do not hide the asserted predicate inside condition.'\nASSESS_PROMPT += '\\nOnly explicit evidence about a property can refute it. Unstated language, duration or causal certainty stays unknown. A documented shared-head list or author-owned model reference may identify a target; keep baseline/comparator roles separate. Bind every count to its full object and every duration to the same event; a model or section identifier is not a measurement.'\n"
    path.write_text(text,encoding='utf-8')
    path=folder/'assessment_decisions.py';text=path.read_text(encoding='utf-8')
    text=replace(text,'    if len(words)>1:',
        '    from .cellfix14_binding_rules import explicit_reference\n    if len(words)>1 and not explicit_reference(part,text):')
    path.write_text(text,encoding='utf-8')
    path=folder/'atomic_decoding.py';text=path.read_text(encoding='utf-8')
    text=replace(text,"        try:\n            yield True\n        finally:\n            self._case_deadline = previous",
        "        try:\n            from .cellfix14_runtime import decode_request\n            with decode_request(deadline):\n                yield True\n        finally:\n            self._case_deadline = previous")
    text=replace(text,"    conjunction = bool(re.search(r'\\band\\b', claim, re.I))",
        "    from .cellfix14_decomposition import conjunctions,expected_quantifier\n    conjunction = bool(conjunctions(claim))")
    text=replace(text,"        scope_values = {'entity': spans,",
        "        clause_quantifier=expected_quantifier(claim,claim[clause['start']:clause['end']],_quantifier)\n        scope_values = {'entity': spans,")
    text=replace(text,"'quantifier': {'type': 'string', 'enum': quantifiers},",
        "'quantifier': {'type': 'string', 'enum': [clause_quantifier]},")
    text=replace(text,"        schema, source = schema_for(messages)",
        "        from .cellfix14_runtime import decode_request\n        with decode_request(self._case_deadline):\n            schema, source = schema_for(messages)")
    text=replace(text,"        def callback(batch_id, input_ids):\n            return enforcer.get_allowed_tokens(input_ids.tolist()).allowed_tokens",
        "        def callback(batch_id, input_ids):\n            from .cellfix14_runtime import decode_request\n            prompt=getattr(self,'_decode_prompt_length',None)\n            if prompt is not None:self._decode_generated_lower_bound=max(0,len(input_ids)-prompt)\n            with decode_request(self._case_deadline):\n                return enforcer.get_allowed_tokens(input_ids.tolist()).allowed_tokens")
    text += "\n\nfrom .cellfix14_generation import generate_json\nConstrainedAtomicBackend.generate_json=generate_json\nDECODER.update(policy='atomic-schema-decoding-v5-cellfix14',quantity_binding='compound_measurements_v1',target_binding='explicit_source_references_v1',deadline_policy='request_cache_signal_and_worker_watchdog')\n"
    path.write_text(text,encoding='utf-8')
    path=folder/'assessment_members.py';text=path.read_text(encoding='utf-8')
    text += '\n\nfrom .cellfix14_binding_rules import nominal_issue\n_previous_identity=member_identity_issue\ndef member_identity_issue(part,member,truth,context):\n    return nominal_issue(part,member,truth,context,_previous_identity)\n'
    path.write_text(text,encoding='utf-8')
    path=folder/'assessment_focus.py';text=path.read_text(encoding='utf-8')
    text += '\n\nfrom .cellfix14_binding_rules import property_issue\n_previous_focus=observation_focus_issue\ndef observation_focus_issue(part,member,quotes,truth,context):\n    return property_issue(part,member,quotes,truth,context,_previous_focus)\n'
    path.write_text(text,encoding='utf-8')
    # Cache repeated finite analysis within one schema only. No cross-request state.
    for filename,names in {
        'assessment_decisions.py':['numeric_choices','decision_evidence'],
        'assessment_evidence.py':['population_witness'],
        'assessment_focus.py':['absence_quotes'],
        'assessment_members.py':['member_absence_quotes'],
    }.items():
        path=folder/filename;text=path.read_text(encoding='utf-8')
        text+='\n\nfrom .cellfix14_runtime import cached\n'
        text+=''.join(name+'=cached('+name+')\n' for name in names)
        path.write_text(text,encoding='utf-8')
    path=SOURCE/'research_rag/evaluation/evaluate_atomic_verifier.py';text=path.read_text(encoding='utf-8')
    text=replace(text,"        self.generation_stats = generation_stats if generation_stats is not None else []",
        "        self.generation_stats = generation_stats if generation_stats is not None else []\n        self.case_deadline_unix=None\n        self.case_deadline_monotonic=None")
    text=replace(text,"        with (hook(self.backend, deadline) if hook else nullcontext(False)) as supported:\n            yield supported is True",
        "        self.case_deadline_unix=time.time()+max(0,deadline-time.monotonic())\n        self.case_deadline_monotonic=deadline\n        try:\n            with (hook(self.backend, deadline) if hook else nullcontext(False)) as supported:\n                yield supported is True\n        finally:\n            self.case_deadline_unix=None\n            self.case_deadline_monotonic=None")
    text=replace(text,"            'example_id': self.case_id, 'messages': messages, 'max_new_tokens': max_new_tokens}",
        "            'example_id': self.case_id, 'case_deadline_unix':self.case_deadline_unix, 'case_deadline_monotonic':self.case_deadline_monotonic, 'messages': messages, 'max_new_tokens': max_new_tokens}")
    text=replace(text,"                replay_result(result, case['claim'], case.get('context', ''), criteria)",
        "                trace.write(json.dumps({'event':'case_finished','example_id':case['example_id']})+'\\n');trace.flush()\n                replay_result(result, case['claim'], case.get('context', ''), criteria)")
    text=replace(text,"    measured = len(generation_stats) == counter[0]",
        "    measured = len(generation_stats) == counter[0] and all(e.get('usage_complete',True) and type(e.get('generated_tokens')) is int and type(e.get('prompt_tokens')) is int for e in generation_stats)")
    text=replace(text,"metrics['checks']['within_measured_token_budget'] = (not measured or",
        "metrics['checks']['within_measured_token_budget'] = (measured and")
    text=replace(text,"        from research_rag.local import run_worker",
        "        from importlib import import_module\n        run_worker=import_module('04_factchecker.inference.cellfix14_runtime').run_worker")
    path.write_text(text,encoding='utf-8')


def build():
    if (ROOT/'docs/atomic-verifier-cellfix14-release.json').exists():raise ValueError('Released cf14 is immutable')
    parent=json.loads((ROOT/'docs/atomic-verifier-cellfix13-candidate.json').read_bytes())
    release=json.loads((ROOT/'docs/atomic-verifier-cellfix13-release.json').read_bytes())
    for name,expected in release['files'].items():
        assert digest((ROOT/name).read_bytes())==expected,name
    for name,item in parent['input_manifest'].items():
        raw=(Path(parent['source_root'])/name).read_bytes()
        assert digest(raw)==item['sha256'],name
        path=SOURCE/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    patch_source()
    for name in ('test_atomic_cellfix14.py',):
        path=SOURCE/'research_rag/tests'/name
        path.write_bytes((ROOT/'scripts'/name).read_bytes())
    sys.path.insert(0,str(SOURCE))
    import importlib
    a=importlib.import_module('04_factchecker.inference.atomic_verifier')
    d=importlib.import_module('04_factchecker.inference.atomic_decoding')
    path=SOURCE/CRITERIA;criteria=json.loads(path.read_bytes());original=json.loads(path.read_bytes())
    criteria.update(version=a.POLICY,policy=a.POLICY,structured_decoder=d.DECODER)
    criteria['prompt_sha256']={'decompose':digest(a.DECOMPOSE_PROMPT.encode()),'assess':digest(a.ASSESS_PROMPT.encode())}
    extra=['04_factchecker/inference/cellfix14_'+v+'.py' for v in ('quantities','binding_rules','runtime','decomposition','generation')]+['research_rag/tests/test_atomic_cellfix14.py']
    criteria['source_sha256']={name:digest((SOURCE/name).read_bytes()) for name in list(criteria['source_sha256'])+extra}
    criteria['limitations'] += ['Validation30-v1 outcomes are exposed and used for development in cellfix14. No independent holdout result or model accuracy is claimed.']
    contract_path=SOURCE/'research_rag/evaluation'/criteria['contract_file']
    contract=json.loads(contract_path.read_bytes());contract['version']='atomic-contract-constrained-v8-cellfix14'
    contract['cellfix14']={'quantities':'source-offset compound objects/durations; exclude explicit identifiers',
        'binding':'finite explicit source references; no external aliases or gold access',
        'evaluation':'validation30-v1 is development; fresh paper-disjoint holdout is required'}
    new_contract=contract_path.with_name('atomic_verifier_contract_v8_cellfix14.json')
    new_contract.write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
    criteria['contract_file']=new_contract.name;criteria['contract_sha256']=digest(new_contract.read_bytes())
    changes={'version','policy','structured_decoder','prompt_sha256','source_sha256','limitations','contract_file','contract_sha256'}
    assert all(criteria[key]==original[key] for key in original.keys()-changes),'Model/data/budget/gate changed'
    path.write_text(json.dumps(criteria,indent=2)+'\n',encoding='utf-8')
    names=sorted(set(parent['input_manifest'])|set(extra)|{new_contract.relative_to(SOURCE).as_posix()})
    report=dict(candidate=a.POLICY,source_root=str(SOURCE),parent_criteria_sha256=parent['criteria_sha256'],
        criteria_sha256=digest(path.read_bytes()),input_manifest={name:{'size':(SOURCE/name).stat().st_size,'sha256':digest((SOURCE/name).read_bytes())} for name in names},
        validation30_used_for_tuning=True,evaluation_role='development',new_model_inference_completed=False,
        independent_validation_completed=False,promoted_to_serving=False,parent_release_files=release['files'],model_budget_gold_gate_unchanged=True)
    (ROOT/'docs/atomic-verifier-cellfix14-candidate.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':a.POLICY,'inputs':len(names),'criteria_sha256':report['criteria_sha256']}))


if __name__=='__main__':build()
