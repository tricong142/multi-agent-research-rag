# Evaluation pilot data

Current gates and recovery notebook: `docs/PROJECT_STATUS.md`. Confidence scoring
now validates labels/runtime status and reports per-label confidence, reliability
bins and support precision/coverage at `--threshold` (default 0.7). It does not
fit a calibration map. Reader reports `span_coverage` and `overall_exact_span_rate`
over every labelled PDF, including failed PDFs; `exact_span_rate` retains the
conditional score over readable PDFs for comparison.

## New diagnostic and annotated qrels (2026-09-26)

See `docs/FACTCHECKER_NEXT_VALIDATION.md` for the experimental Fact-Checker prompt comparison and the QASPER paragraph benchmark built locally. The approved update is uploaded as Private diagnostics dataset version 2. The paired GPU run was launched, but no completed A/B result has been recovered; see `docs/VALIDATION_RUN_20260927.md`. `prepare_qasper.py` produced 393 dev and 417 test-candidate qrels from human evidence annotations, with explicit exclusions and provenance. On 2026-09-27, a separate BM25 index scored hit@5=0.279898 and paragraph recall@5=0.159664 on all 393 dev queries; full metrics and hashes are in `docs/qasper-bm25-dev-20260927.json`. Its FAISS index is not built. The candidate is not yet certified as an independent end-to-end test and remains unscored. Existing pilot results below remain unchanged.

`retrieval_smoke_qrels.jsonl` contains ten questions written after reading specific corpus passages. Each `relevant_doc_ids` list names one **confirmed positive chunk**, not an exhaustive set of all relevant chunks. The questions are derived from the same corpus being searched. This file is useful for a retrieval smoke test but **not** a held-out estimate of recall or generalization. A local BM25 run on 2026-09-24 gave known-positive hit@5 = 7/10; the three misses were cases 2, 7 and 9. Case 7 and 9 returned other chunks from the same paper, which may be relevant and need independent judgement before expanding qrels. Do not edit labels merely to raise a score.

Run the pilot from the workspace root:

```bash
python -m research_rag.evaluate retrieval --qrels research_rag/evaluation/retrieval_smoke_qrels.jsonl --mode bm25 --top-k 5
python -m research_rag.evaluate retrieval --qrels research_rag/evaluation/retrieval_smoke_qrels.jsonl --mode dense --top-k 5
```

The three original PDFs under `pdfs/` cover a two-page text layer, two columns with a small table, and a rasterized scan with no text layer. `reader_smoke_manifest.jsonl` records expected phrases and zero-based page numbers. `make_reader_fixtures.py` regenerates the PDFs with ReportLab and PyMuPDF; ReportLab is an authoring dependency, not a serving dependency. The rendered pages were visually inspected at creation time. `reader_smoke.py` scores exact normalized span matches and token recall:

```bash
python -m research_rag.evaluation.reader_smoke
```

This command invokes the real Reader. It requires Tesseract for the scan and a working `GEMINI_API_KEY` for the Reader critique path. The Reader sends up to five sample text blocks per page to Gemini, so use these synthetic PDFs or other documents approved for external API processing. These fixtures establish mechanics; add independently labelled real PDFs across layouts and scan quality before claiming production Reader quality.

`reader_real_manifest.jsonl` adds one unchanged, CC-BY-4.0 ACL paper (12 pages)
with nine spans on pages 0, 3 and 8 (zero-based). The assistant transcribed the
spans after visual review with Poppler, before Reader predictions. Attribution,
source URL and SHA-256 are in `pdfs/SOURCES.md`. These labels await independent
review; one paper is not a representative held-out PDF benchmark, and does not
cover real scans. The scorer validates `source_sha256` when present. Run with
`--manifest research_rag/evaluation/reader_real_manifest.jsonl` after configuring
the API and Reader model dependencies. On 2026-09-27 the real Gemini
`gemini-3.5-flash-lite` run scored 6/9 exact spans on the three selected pages
(not the entire paper). All API calls succeeded, but the quality gate failed.
An offline audit with the actual LayoutLMv3 checkpoint confirmed that the old
512-token truncation dropped input lines. The local overflow-window fix and
NFKC scoring normalization have regression tests; neither has been rerun with
the real model on Kaggle yet. These assistant-transcribed labels are diagnostic,
not independently adjudicated ground truth.

The same endpoint completed all three synthetic smoke PDFs in one run: 9/9
spans, 184.09 seconds including deliberate 61-second request spacing, 2,080
reported tokens. This establishes a working API path, not an availability SLA.
Set `GEMINI_MODEL=gemini-3.5-flash-lite` explicitly for that configuration. The
new optional `GEMINI_REQUEST_INTERVAL_SECONDS=61` shares pacing between router
and critic within one process; it does not coordinate multiple workers.

The smoke command prints `passed` and exits with code 1 if any PDF fails, no spans are evaluated, or an expected normalized span is missing. A successful process therefore requires all fixture spans on the correct pages; this is a smoke-test gate, not a production quality threshold.

On the local Windows host, extraction with Gemini router/critique stubbed to accept returned blocks matched all 7/7 expected spans in the two text PDFs. The scan could not run there because the Tesseract binary is absent. This is an extraction smoke test, **not** a live API or OCR result. Phrase presence does not check full reading order or table structure.

For Kaggle, upload the small `kaggle_transfer/research-rag-eval-fixtures.zip` as a second Private dataset and Add Input. Locate its `reader_smoke_manifest.jsonl` under `/kaggle/input`. From a notebook where `root` is the main workspace path, run the **absolute path** to `reader_smoke.py` in the fixture dataset with `PYTHONPATH=str(root)` and `--manifest` set to the located file. The v2 main dataset does not contain the evaluation subpackage, so `python -m research_rag.evaluation.reader_smoke` cannot find it there. The older fixture script also needs an explicit assertion that `failures` is empty and `exact_span_rate == 1.0`; see the runbook. Use `research_rag.evaluate retrieval --qrels` with the qrels path from this second dataset. The evaluation files need not be copied into the read-only main workspace.

For a real retrieval evaluation, collect user questions before inspecting retrieval output, have a reviewer identify **all** answer-bearing chunks in a pooled candidate set, record adjudication, and keep a final question set separate from policy tuning. Record `query`, `relevant_doc_ids`, corpus/index version and annotation rules. Use the same qrels for BM25, dense and policy comparisons; a dense run with fallback is not a dense score.

## Fact-Checker split audit and confidence collection (2026-09-26)

`factchecker_split_audit.json` records SHA-256 fingerprints and duplicate counts for the current 1,312 train and 468 dev rows. Claim IDs do not overlap, but **two normalized claim/context pairs do overlap**. The audit also finds 181 shared document IDs; the data is not a document-disjoint evaluation.

`scifact_dev_deduplicated.jsonl` excludes the entire dev claim group when its lowercase, whitespace-normalized claim appears in train. This leaves **466 rows** (216 support, 122 contradict, 128 not_enough_info). The original data is unchanged. Excluded example IDs: `870:195689316:nei`, `1292:56893404:nei`. This removes observed duplicates; it does not prove semantic non-overlap or turn a previously used dev set into an independent final test. SciFact attribution and CC BY-NC 2.0 restrictions in `THIRD_PARTY_NOTICES.md` still apply.

Collect actual serving-node predictions on a GPU using the updated script:

```bash
python 04_factchecker/eval_factchecker.py --runtime-contract --data research_rag/evaluation/scifact_dev_deduplicated.jsonl --output /kaggle/working/factchecker-confidence-dev.jsonl
python -m research_rag.evaluate confidence --predictions /kaggle/working/factchecker-confidence-dev.jsonl
```

`--runtime-contract` calls the same Judge, ConfidenceEstimator, ActionRecommender and retry logic as the graph. It records real scores only when `status=ok`; failures receive `confidence_score=null` and cause calibration scoring to reject the file. Do not silently remove failures or count fallback zeroes as model confidence. Report failure coverage separately and resolve failures before the full-set calibration run. The full 466-row run has not been executed. A real GPU diagnostic on 2026-09-26 selected the first 10 rows per label before inference (30 total): no runtime failures, accuracy 0.600, macro-F1 0.59337, ECE 0.402 and Brier 0.400087. Several correct non-support predictions have score 0. These results do not establish a calibrated score or independent held-out quality. `calibration_ready` only means numeric scores are available. Evidence is saved in Kaggle Version 4 and locally under `kaggle_transfer/validation-20260926/`; see `docs/KAGGLE_VALIDATION_STATUS.md`. The old predictions cannot be backfilled with invented confidence scores.

Freeze a separate, independently labelled final set before threshold tuning. If fitting a calibration map or selecting a threshold, use a calibration partition grouped by claim/paper, and evaluate once on the untouched final partition. No calibration map has been fitted and the threshold 0.7 remains provisional.
