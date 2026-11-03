"""Finite, explicit source references. Never use gold labels or case identifiers."""
import re


def source_targets(part,context):
    from .atomic_verifier import target_entity
    entity=target_entity(part)
    if not entity: return []
    exact=[m[0] for m in re.finditer(r'(?<!\w)'+re.escape(entity)+r'(?!\w)',context,re.I)]
    if exact: return sorted(set(exact))
    # An explicitly author-owned model is a document-local reference, never its comparator.
    if re.fullmatch(r'(?:proposed|our) model',entity,re.I):
        if not re.search(r'\b(?:another|alternative|second) (?:proposed|our) model\b',context,re.I):
            return sorted({m[0] for m in re.finditer(r'\bour model\b',context,re.I)})
        return []
    if entity.casefold() in ('study','paper'):
        return sorted({
            m[1] for m in re.finditer(r'(?:^|[.!?]\s+)(We)\s+(?:use|used|train|trained|evaluate|evaluated|report|reported)\b',context)})
    # Shared head: "X A-B, B-C and C-D" explicitly names X B-C.
    cleaned=re.sub(r'\s+(?:system|transcriptions|dataset)$','',entity,flags=re.I)
    words=cleaned.split()
    if len(words)==2:
        head,item=words
        pattern=r'(?<!\w)'+re.escape(head)+r'\s+((?:[\w-]+\s*[,/]\s*)*[\w-]+(?:\s+and\s+[\w-]+)?)'
        for match in re.finditer(pattern,context):
            for token in re.finditer(r'[\w-]+',match[1]):
                if token[0]==item:
                    return [token[0]]
    # Proper-name apposition: "NAME BIBREFn, transcriptions ...".
    named=re.fullmatch(r'([A-Z][A-Z0-9_-]+)\s+(transcriptions|dataset|corpus)',entity)
    if named:
        match=re.search(r'\b('+re.escape(named[1])+r')\s+(?:BIBREF\d+\s*)?[,(:]\s*(?:the\s+)?'+re.escape(named[2])+r'\b',context)
        if match:return [match[1]]
    # An acronym explicitly declared in this context can qualify its section IDs.
    section=re.fullmatch(r'([A-Z][A-Z0-9]+)\s+(sections?\s+\d+(?:[-–]\d+)?)',entity)
    if section and re.search(r'\('+re.escape(section[1])+r'\)|\b'+re.escape(section[1])+r'\s+(?:hereafter|corpus|dataset)',context):
        return sorted({m[0] for m in re.finditer(r'(?<!\w)'+re.escape(section[2])+r'(?!\w)',context,re.I)})
    return []


def nominal_issue(part,member,truth,context,previous):
    if re.search(r'\b(?:is|are|was|were|consisting|consists|has|have|had|did)\b',member,re.I):
        return 'observation_member_is_not_entity'
    return previous(part,member,truth,context)


def explicit_reference(part,text):
    from .atomic_verifier import target_entity
    entity=target_entity(part)
    return bool(entity and not re.search(r'(?<!\w)'+re.escape(entity)+r'(?!\w)',text,re.I) and source_targets(part,text))


def property_issue(part,member,quotes,truth,context,previous):
    issue=previous(part,member,quotes,truth,context)
    if issue:return issue
    # Absence of a language assertion is not an assertion of another language.
    if truth!='unknown' and re.search(r'\bwritten in\s+\w+',part['quote'],re.I):
        if not any(re.search(r'\b(?:written in|language|[a-z]+-language)\b',q,re.I) for q in quotes):
            return 'property_evidence_missing'
    return None
