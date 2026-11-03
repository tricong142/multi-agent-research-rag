"""Shared sentence-shape checks before handing claims to the verifier.

This finite English/Vietnamese guard rejects fragments, not semantic errors.
Critic and Verifier must still establish entity/metric/value binding to evidence.
"""
import re
import unicodedata

SENTENCE_BREAK = re.compile(
    r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\bal\.)(?<!\bDr\.)(?<!\bFig\.)(?<!\bEq\.)"
    r"(?<=[.!?;])\s+(?=[^\W_])", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)")
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)
_FUNCTION = set("a an the and or but not no all some none every each any both one another others it its they them their this that these those we our i you he she which what who there here after before during in on at to of for with by from as than also only already approximately roughly about nó họ chúng tôi này đó đã đang sẽ bị được chỉ cũng không một các những của vào về trên dưới bằng với từ khi bao tất cả mọi".split())
_INTRANSITIVE = set("failed fails fail converged converges converge disagree disagrees disagreed work works worked exist exists existed run runs ran stopped stop stops".split())
_RELATIONS = set("am is are was were be been being has have had do does did can could may might must shall should will would found finds find took takes take gave gives give became becomes become built builds build ran runs run shown shows show known knows know led leads lead cost costs put là có đạt gồm chứa giảm tăng dùng được tuyển thu".split())
for _verb in "achieve improve reduce increase decrease use compare provide require describe observe exclude include measure remove retain align contain report evaluate enroll train test predict label assign collect sample select cover last return learn distinguish gain yield fail pass work outperform lag precede follow employ detect demonstrate support refute identify obtain match perform represent record establish count differ disagree converge stop".split():
    _RELATIONS.update((_verb, _verb + ("es" if _verb.endswith(("s", "sh", "ch", "o")) else "s"),
                       _verb + ("d" if _verb.endswith("e") else "ed")))

REWRITE_INSTRUCTION = (
    "Rewrite each claim as a standalone factual sentence with an explicit entity and metric/relation. "
    "Include the value, unit, comparator, time and condition only when supported by the supplied evidence. "
    "Do not return bare numbers, unit phrases, noun fragments, unresolved pronouns or subjectless predicates. "
    "Qualitative claims do not require invented quantities. Preserve verbatim evidence; do not add facts "
    "from the question or general knowledge. If the entity or relation is absent from the source, request more context."
)


def split_claims(answer: str) -> list[str]:
    """Keep sentence candidates intact, including decimals; allow bullet lists."""
    sections = re.split(r"\n\s*(?=[-*•]\s|\d+[.)]\s)", answer.strip())
    return [value for section in sections for part in SENTENCE_BREAK.split(_BULLET.sub("", section))
            if (value := part.strip())]


def claim_issue(claim: str) -> str | None:
    text = unicodedata.normalize("NFKC", claim).strip()
    if not text:
        return "empty_claim"
    if text.endswith("?"):
        return "question_not_claim"
    words = list(_WORD.finditer(text))
    if not words:
        return "bare_quantity"
    predicates = [word for word in words if word.group().casefold() in _RELATIONS]
    predicates += list(re.finditer(r"\bsử\s+dụng\b", text, re.I))
    predicates.sort(key=lambda word: word.start())
    if not predicates:
        return "metric_or_relation_missing"
    has_subject = False
    for predicate in predicates:
        prefix = text[:predicate.start()].rsplit(",", 1)[-1]
        if not any(w.casefold() not in _FUNCTION for w in _WORD.findall(prefix)):
            continue
        has_subject = True
        tail = _WORD.findall(text[predicate.end():])
        # An intransitive factual action can be complete without a numeric value.
        if any(w.casefold() not in _FUNCTION for w in tail) or re.search(r"\d", text[predicate.end():]):
            return None
        if predicate.group().casefold() in _INTRANSITIVE:
            return None
    return "predicate_incomplete" if has_subject else "entity_missing"


def claim_contract_issues(answer: str) -> list[dict]:
    if not isinstance(answer, str) or not answer.strip():
        return [{"claim_index": 0, "code": "empty_answer"}]
    return [{"claim_index": index, "code": issue} for index, claim in enumerate(split_claims(answer))
            if (issue := claim_issue(claim))]
