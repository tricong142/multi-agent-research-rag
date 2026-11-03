# Cellfix16 holdout30-v2 — frozen, pending human annotation

30 assistant-authored claims, 10 previously unexposed arXiv papers in the cached
QASPER test corpus; 10 SUPPORT / 10 CONTRADICT / 10 NEI. Internal labels are
support / contradict / not_enough_info. New means new to known project exposure,
not newly published in 2026. Annotation is AI-proposed, not human-certified gold.

Open REVIEW.html offline, read every supplied paragraph, review the labels and
spans, then export annotation-review.json. There are no pre-approved checks.
NEI is relative to the supplied paragraph; a related quote is not proof that a
fact is absent from the complete paper. Sources retain the original cached
QASPER text, including BIBREF markers; exactness is against that text, not a
freshly downloaded PDF. Source URLs are attribution links, not network requests.

Verify offline from the repository root:

    python docs/validation/atomic-cellfix16-holdout30-v2/review_gate.py --packet docs/validation/atomic-cellfix16-holdout30-v2

After direct human annotation, admit without model inference:

    python docs/validation/atomic-cellfix16-holdout30-v2/review_gate.py --packet docs/validation/atomic-cellfix16-holdout30-v2 --review PATH/annotation-review.json --lock PATH/holdout-annotation-admission.json

The lock covers source snapshots, claims, proposed labels, exact offsets, blind
inputs, protocol, exposure screen and review tooling. Do not edit a locked packet;
annotation corrections need a new version before any candidate outcomes are seen.
The admission JSON binds the normalized review content to this packet/candidate.

blind-inputs.zip contains only inputs.jsonl (id/claim/context) and model-settings.json;
give only that ZIP to model inference. Keep cases.jsonl and the full review packet
on the evaluation side. Do not use the new labels/claims to repair Cellfix16 rules.
If outcomes inform tuning, retire this packet to development and create another
holdout. Preserve all outcomes and technical reruns. Ten paper clusters with
three contrast siblings each are a small purposive pilot, not 30 independent
documents, a population guarantee, or end-to-end serving certification.

Before inference require human annotation admission, the same Cellfix16
smoke/probe/full39 gates and the preregistered dev30 result. The existing notebook
cell7 is bound to development30; this packet does not replace that cell or change
its metrics/gates. No holdout inference or promotion has been performed by this
preparation script. Use a separate one-shot holdout job on the blind inputs and
score against the locked cases with the protocol in criteria.json.
