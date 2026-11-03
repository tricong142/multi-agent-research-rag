"""Finite, source-local relations shared by decoding and validation."""
import re
from decimal import Decimal


def count_unit(unit):
    if unit.casefold() == 'name annotations':
        return 'annotations'
    if re.fullmatch(r'(?:Turkish|French|English|German|Chinese) tweets', unit, re.I):
        return 'tweets'
    return unit


def quantity_modifier_issue(raw, claim, context):
    if raw.get('kind') != 'value':
        return None
    def role(operand,text):
        at=text.find(operand['quote'])
        if at<0:return None
        prefix=text[:at];tail=text[at+len(operand['quote']):]
        subset=re.search(r'\bof which\s*$',prefix) or re.match(r'\s+of which\b',tail)
        if subset:
            prop=re.match(r'\s*(?:of which\s+)?are\s+(\w+)',tail)
            return ('subset',prop[1].lower()) if prop else None
        total=re.match(r'\s*,\s*(?:of which\s+)?[\d,]+\s+(?:of which\s+)?are\s+(\w+)',tail)
        return ('total',total[1].lower()) if total else None
    expected=role(raw['left'],claim)
    if expected and role(raw['right'],raw['source_quote'])!=expected:
        return 'numeric_requirement_role_unresolved'
    quote = raw['left']['quote']
    if re.search(r'\bname annotations\b', quote, re.I):
        number = re.escape(raw['right']['quote'].split()[0])
        named = re.search(r'\bnamed? (?:entity |entities |annotations\b)', raw['source_quote'], re.I)
        linked = re.search(number+r' annotations[^.!?]*\.\s*We further annotate these '+number+r' names\b', context, re.I)
        if not named and not linked:
            return 'numeric_count_modifier_unresolved'
    language = re.search(r'\b(Turkish|French|English|German|Chinese) tweets\b', quote, re.I)
    if language and not re.search(re.escape(raw['right']['quote'])+r'\s+in '+re.escape(language[1])+r'\b', raw['source_quote'], re.I):
        if not re.search(re.escape(language[1])+r' tweets\b', raw['source_quote'], re.I):
            return 'numeric_count_modifier_unresolved'
    return None


def measurement_qualification(proof,raw):
    result=re.sub(r'\bnot good enough\b','unsatisfactory',proof,flags=re.I)
    units=set(re.findall(r'[a-z]+',(raw['left']['unit']+' '+raw['right']['unit']).lower()))
    def unrelated_status(match):
        return match[0] if match[1].lower() in units else 'annotation status'
    return re.sub(r'\bwhether (?:the )?(actions|events|items) (?:are|were) [a-z-]+ or not\b',unrelated_status,result,flags=re.I)


def explicit_witness(part, context):
    from .atomic_verifier import target_members
    from .assessment_rules import clauses, contains, scope_conflict
    members = target_members(part, context)
    if part['quantifier'] != 'atomic' or not members:
        return None
    claim = part['quote']
    facts = []
    sentences = [m[0].strip(' .') for m in re.finditer(r'[^.!?]+(?:[.!?](?=\s|$)|$)', context)]
    for clause in sorted(set(clauses(context)+sentences), key=len):
        if len(clause) > 384:
            continue
        if scope_conflict(part, clause) or not any(contains(m, clause) for m in members):
            continue
        if re.search(r'\b(?:might|could|hypothetical|planned|alleged)\b', clause, re.I):
            continue
        truth = None
        bleu = re.search(r'\b(detokenized|tokenized) BLEU\b', claim, re.I)
        source_bleu = re.findall(r'\b(detokenized|tokenized) BLEU\b', clause, re.I)
        qualified = bool(re.search(r'\b(?:not|never|without|may|might|would|could|should|if|planned|reported as false)\b', clause, re.I))
        if bleu and not qualified and len(set(v.lower() for v in source_bleu)) == 1:
            truth = bleu[1].lower() == source_bleu[0].lower()
        objective = re.search(r'\brequir\w*\s+(?:a |any )?(modified training objective)\b', claim, re.I)
        if objective and re.search(r'\bmodified training objective\b', clause, re.I):
            if re.search(r'\bwithout requiring\b[^.;]*\bmodified training objective\b', clause, re.I):
                truth = False
            elif re.search(r'\brequir(?:ed|es|ing)\s+(?:a )?modified training objective\b', clause, re.I):
                truth = True
        comparison = re.search(r'\b(better|worse) than (.+?)(?= on | during |[.!]|$)', claim, re.I)
        if comparison:
            match = re.search(r'\b(better|worse) than '+re.escape(comparison[2])+r'\b', clause, re.I)
            restrictions = [v for v in (part['scope']['condition'], part['scope']['time']) if v]
            if match and not qualified and all(contains(v, clause) for v in restrictions):
                truth = comparison[1].lower() == match[1].lower()
        role = re.search(r'\b(training|test|development|validation) set\b', claim, re.I)
        source_role = re.findall(r'\b(training|test|development|validation) set\b', clause, re.I)
        if role and not qualified and re.search(r'\bsections?\s+\d', claim, re.I) and len(set(v.lower() for v in source_role)) == 1:
            truth = role[1].lower() == source_role[0].lower()
        if truth is not None:
            facts.append(('true' if truth else 'false', clause))
    if not facts or len({t for t, _ in facts}) != 1:
        return None
    return dict(truth=facts[0][0], members=members, numeric=False, quotes=sorted({q for _, q in facts}))


def relation_issue(part, member, quotes, truth, context):
    from .assessment_rules import contains
    if part['quantifier'] != 'atomic' and truth != 'unknown' and not any(contains(member,q) for q in quotes):
        return 'observation_evidence_unbound'
    witness = explicit_witness(part, context)
    if witness and truth != 'unknown':
        if truth != witness['truth']:
            return 'observation_polarity_mismatch'
        if not any(w in q for w in witness['quotes'] for q in quotes):
            return 'observation_predicate_not_grounded'
    return None


def count_witness(part,context):
    from .numeric_verifier import numeric_requirements,check_numeric
    from .assessment_rules import contains,scope_conflict
    requirements=numeric_requirements(part['quote'])
    if part['quantifier']!='all' or len(requirements)!=1:return None
    left=requirements[0]
    predicate=re.sub(r'^(?:is|are)\s+','',part['scope']['metric'],flags=re.I)
    if not re.fullmatch(r'[a-z-]+',predicate,re.I):return None
    for m in re.finditer(r'[^.!?]+(?:[.!?](?=\s|$)|$)',context):
        sentence=m[0].strip();counts=numeric_requirements(sentence)
        restrictions=[re.sub(r'^(?:in|on|during|under)\s+','',v,flags=re.I) for v in (part['scope']['condition'],part['scope']['time']) if v]
        if scope_conflict(part,sentence) or any(not contains(v,sentence) for v in restrictions):continue
        if len(counts)!=2 or counts[0]['value']!=left['value'] or counts[0]['unit']!=left['unit']:continue
        if not re.search(re.escape(counts[0]['quote'])+r',\s*'+re.escape(counts[1]['quote'])+r' of which are '+re.escape(predicate)+r'\b',sentence,re.I):continue
        if not (0<=Decimal(counts[1]['value'])<Decimal(left['value'])):continue
        record=dict(kind='value',source_quote=sentence,left={k:left[k] for k in ('value','unit','quote')},right={k:counts[1][k] for k in ('value','unit','quote')})
        if check_numeric(record,part['quote'],context,metric=part['scope']['metric'])['truth']!='false':continue
        return dict(truth='false',members=[counts[0]['quote']],quotes=[sentence],numeric=True,record=record)
    return None


def coverage_schema(schema,part,context):
    """Coverage names must at least be legal observation names in this request."""
    obs=schema['properties']['observations']['items']
    members={m for b in obs.get('anyOf',[obs]) for m in b['properties']['member'].get('enum',[])}
    cov=schema['properties']['coverage']
    for branch in cov.get('anyOf',[cov]):
        item=branch['properties']['members']['items']
        if 'enum' in item:
            item['enum']=[m for m in item['enum'] if m in members and re.fullmatch(r'[\w-]+(?:\s+[\w-]+){0,7}',m)]
    return schema


def count_schema(witness):
    from .atomic_decoding import obj,array
    def fixed(value):
        return obj({k:fixed(v) for k,v in value.items()}) if isinstance(value,dict) else {'type':'string','enum':[value]}
    observation=obj(dict(member=fixed(witness['members'][0]),truth=fixed('false'),quotes=array(fixed(witness['quotes'][0]),minimum=1,maximum=1),explanation=fixed('Predicate evidence recorded.'),numeric=fixed(witness['record'])))
    return obj(dict(scope_match=fixed('matched'),coverage=obj(dict(complete={'const':False},members=array({'type':'string'},maximum=0),quotes=array({'type':'string'},maximum=0))),observations=array(observation,minimum=1,maximum=1),missing_information=array({'type':'string'},maximum=0),explanation=fixed('Assess the recorded evidence ledger.')))


def subject_issue(scope, quote):
    entity = scope['entity']
    if not re.search(r'[A-Za-z]', entity):
        return 'entity_reference_required'
    comparison = re.search(r'\bthan\b', quote, re.I)
    if comparison and entity in quote and quote.find(entity) > comparison.start():
        return 'subject_comparator_inverted'
    population = re.search(r'\b(?:all|every|each|some|none)\b', quote, re.I)
    if population and entity in quote:
        # A postposed quantifier qualifies the preceding subject, e.g. articles are all French.
        postposed = re.search(r'\b(?:is|are|was|were)\s+(?:all|each|every)\b', quote, re.I)
        end = quote.find(entity) + len(entity)
        includes_quantifier = quote.find(entity) <= population.start() and end > population.end()
        if entity.lower() not in {'the','a','an','all','every','each','some','none'} and not postposed and not includes_quantifier and end <= population.end():
            return 'quantified_population_required'
    return None


def population_witness(part, context):
    from .assessment_rules import contains, scope_conflict
    if part['quantifier'] == 'atomic':
        return None
    relation = re.search(r'\bpaired with (.+?)[.!]?$', part['scope']['metric'], re.I)
    if not relation:
        return None
    noun = part['scope']['entity'].rstrip('s')
    for match in re.finditer(r'[^.!?]+(?:[.!?](?=\s|$)|$)', context):
        sentence = match[0].strip()
        population = re.search(r'\b(\d+ '+re.escape(noun)+r's?)\b', sentence, re.I)
        predicate = re.search(r'\beach paired with (?:a set of )?'+re.escape(relation[1].rstrip('.'))+r'\b', sentence, re.I)
        restrictions = [re.sub(r'^(?:in|on)\s+(?:the\s+)?', '', v, flags=re.I)
                        for v in (part['scope']['condition'], part['scope']['time']) if v]
        if (population and predicate and len(sentence) <= 384 and not scope_conflict(part, sentence)
                and all(contains(v, sentence) for v in restrictions)
                and not re.search(r'\b(?:not|never|without|would|could|might|may|except|only|some|unreported)\b', sentence, re.I)):
            return dict(truth='true', members=[population[1]], quotes=[sentence],
                        complete=True, numeric=False, population=True)
    return None


def decomposition_schema(claim, previous):
    from copy import deepcopy
    from .atomic_verifier import metric_predicate_requirement
    schema = previous(claim)
    item = schema['properties']['parts']['items']
    alternatives = []
    for branch in item.get('anyOf', [item]):
        for quote in branch['properties']['quote']['enum']:
            fixed = deepcopy(branch)
            fields = fixed['properties']['scope']['properties']
            # Keep a complete population prefix in entity; condition remains its own restriction.
            entities = []
            for entity in fields['entity']['enum']:
                scope = dict(entity=entity, metric=fields['metric']['enum'][0], time='', condition='')
                if subject_issue(scope, quote):
                    continue
                population=re.search(r'\b(?:all|every|each|some|none)(?:\s+of)?\b',quote,re.I)
                missing=False
                if population:
                    start=quote.find(entity,population.end())
                    prefix=quote[population.end():start] if start>=0 else ''
                    if not re.search(r'[,.;]',prefix):
                        modifiers=[w.lower() for w in re.findall(r'\b[\w-]+\b',prefix) if w.lower() not in {'the','a','an','of'}]
                        missing=any(w not in re.findall(r'\b[\w-]+\b',entity.lower()) for w in modifiers)
                if not missing:entities.append(entity)
            if not entities:
                continue
            fields['entity']['enum'] = entities
            metrics=[m for m in fields['metric']['enum'] if not metric_predicate_requirement(dict(entity='',metric=m,time='',condition=''),quote)]
            if not metrics:continue
            fields['metric']['enum']=metrics
            fixed['properties']['quote']['enum'] = [quote]
            alternatives.append(fixed)
    if not alternatives:
        raise ValueError('unsupported_scope_structure')
    schema['properties']['parts']['items'] = alternatives[0] if len(alternatives) == 1 else {'anyOf': alternatives}
    return schema
