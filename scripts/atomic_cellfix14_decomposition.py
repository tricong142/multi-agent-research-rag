"""Shared clause/quantifier rules for decoding and canonical validation."""
import re

_VERB=re.compile(r'\b(?:is|are|was|were|has|have|had|uses?|used|takes?|took|contains?|contained|'
                 r'improves?|improved|increases?|increased|decreases?|decreased|reduces?|reduced|'
                 r'achieves?|achieved|requires?|required|lasts?|lasted|trained|evaluates?|evaluated|'
                 r'outperforms?|outperformed|consists?|consisted|remains?|remained|retains?|retained|'
                 r'maintains?|maintained|records?|recorded|reports?|reported|measured|failed|passed|leaked)\b',re.I)


def conjunctions(claim):
    """Split factual predicates, not a list of objects/purposes of one predicate."""
    result=[]
    for match in re.finditer(r'\band\b',claim,re.I):
        left,right=claim[:match.start()],claim[match.end():]
        purpose_head=right.strip(' .').casefold().split()[-1:]
        purpose=bool(re.search(r'\bfor\s+[A-Za-z -]+$',left,re.I)
                     and re.fullmatch(r'\s*[A-Za-z -]+[.]?\s*',right)
                     and purpose_head and purpose_head[0] in {'optimization','development','evaluation','training','testing','validation','tuning','selection'})
        count_list=bool(re.match(r'\s*(?:\d|one\b|two\b|three\b|four\b|five\b)',right,re.I)
                        and re.search(r'\b(?:contains?|contained|includes?|included|used|uses?)\b',left,re.I))
        # Unknown syntax keeps the previous conservative split, never silently
        # turns two unfamiliar predicates into a single atomic assertion.
        if _VERB.search(right) or not (purpose or count_list):result.append(match)
    return result


def expected_quantifier(claim,quote,quantifier):
    own=quantifier(quote)
    first=quantifier(re.split(r'\band\b',claim,maxsplit=1,flags=re.I)[0])
    return first if own=='atomic' else own


def subject_issue(scope,quote):
    entity=scope['entity']
    if not re.search(r'[A-Za-z]',entity):return 'entity_reference_required'
    # A comparator following "than" cannot become the grammatical subject.
    comparison=re.search(r'\bthan\b',quote,re.I)
    if comparison and entity in quote and quote.find(entity)>comparison.start():
        return 'subject_comparator_inverted'
    population=re.search(r'\b(?:all|every|each|some|none)\b',quote,re.I)
    if (population and entity.casefold() not in {'the','a','an','all','every','each','some','none'}
            and entity in quote and quote.find(entity)<population.end()
            and quote.find(entity,population.end())<0):
        return 'quantified_population_required'
    return None
