"""Read-only overlap screen against newly added development code/fixtures."""
import ast
import json
from pathlib import Path

from scripts.atomic_validation_review import digest,json_bytes
from scripts.prepare_atomic_validation_v1 import strings,tokens,grams,near

ROOT=Path(__file__).resolve().parents[1]


def main():
    candidate=json.loads((ROOT/'docs/atomic-verifier-cellfix7-candidate.json').read_bytes())
    source=Path(candidate['source_root'])
    old=ROOT/'docs/validation/atomic-cellfix6-v1'
    prior=json.loads((old/'overlap-report.json').read_bytes())
    for name,expected in prior['scanned_files_sha256'].items():
        if digest((ROOT/name).read_bytes())!=expected:raise ValueError('Prior screened data changed: '+name)
    cases=[json.loads(s) for s in (old/'cases.jsonl').read_text(encoding='utf-8').splitlines()]
    targets={r['id']+':claim':tokens(r['claim']) for r in cases}
    targets.update({r['source']['doc_id']:tokens(r['context']) for r in cases})
    index={}
    for key,words in targets.items():
        for gram in grams(words):index.setdefault(gram,set()).add(key)
    sets={key:set(words) for key,words in targets.items()}
    hashes={};flags=[];count=0
    for name,item in candidate['input_manifest'].items():
        if not name.endswith(('.py','.json','.jsonl')) or not name.startswith(('research_rag/tests/','research_rag/evaluation/','04_factchecker/inference/')):continue
        raw=(source/name).read_bytes();hashes[name]=digest(raw)
        if name.endswith('.py'):
            values=(n.value for n in ast.walk(ast.parse(raw.decode('utf-8-sig'))) if isinstance(n,ast.Constant) and isinstance(n.value,str))
        elif name.endswith('.jsonl'):
            values=(s for line in raw.decode('utf-8').splitlines() for s in strings(json.loads(line)))
        else:values=strings(json.loads(raw))
        seen=set()
        for value in values:
            words=tokens(value)
            if len(words)<6 or tuple(words) in seen:continue
            seen.add(tuple(words));count+=1;hits=set();ws=set(words)
            for gram in grams(words):hits.update(index.get(gram,()))
            for key,ts in sets.items():
                if len(ws&ts)/max(1,len(ws|ts))>=.8:hits.add(key)
            for key in hits:
                found,score,shared=near(words,targets[key])
                if found:flags.append({'validation_item':key,'development_file':name,'text_sha256':digest(value.encode()),
                    'token_jaccard':score,'shared_eight_token_phrases':len(shared)})
    report={'candidate':candidate['candidate'],'criteria_sha256':candidate['criteria_sha256'],
        'prior_overlap_report_sha256':digest((old/'overlap-report.json').read_bytes()),'prior_screen_inputs_unchanged':True,
        'scanned_development_files_sha256':hashes,'scanned_strings':count,'flags':flags,
        'normalization':prior['normalization'],'flag_rules':prior['flag_rules'],
        'model_outputs_on_validation_used':False,'limitations':prior['limitations']}
    (ROOT/'docs/atomic-verifier-cellfix7-validation-overlap.json').write_bytes(json_bytes(report))
    print(json.dumps({'new_development_files':len(hashes),'strings':count,'overlap_flags':len(flags)}))
    if flags:raise SystemExit(1)


if __name__=='__main__':main()
