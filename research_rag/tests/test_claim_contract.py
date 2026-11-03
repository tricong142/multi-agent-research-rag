"""Sentence-shape regressions with synthetic examples, not semantic/model scores."""
from copy import deepcopy
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from train_agent3_summarizer import config
from train_agent3_summarizer.claim_contract import claim_contract_issues, split_claims
from train_agent3_summarizer.node import SummarizerNode
from research_rag.graph import build_graph


FACT = "The Orion study enrolled 42 participants."
CRITIC = {"is_supported": True, "reason": "The complete claim is supported.", "action": ""}


def chunk(text, source="paper:1"):
    return {"doc_id": source, "source_id": source, "text": text, "metadata": {}, "score": 1.0, "method": "bm25"}


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks

    def search(self, *args, **kwargs):
        return {"chunks": self.chunks, "decision": "bm25", "warning": None}


class FakeSummarizer:
    def __init__(self, answer, evidence, supported=True):
        self.answer, self.evidence, self.supported = answer, evidence, supported

    def run(self, **kwargs):
        return SimpleNamespace(answer=self.answer, evidence_spans=[self.evidence],
                               is_supported=self.supported, confidence="high" if self.supported else "low")


class FakeFactchecker:
    def __init__(self, labels):
        self.calls, self.labels = [], labels

    def __call__(self, state):
        self.calls.append(state)
        return {"fact_check_label": self.labels[0], "fact_check_status": "ok", "confidence_score": .9}


def make_graph(**options):
    writer = importlib.import_module("05_writer.node").WriterNode()
    return build_graph(**(dict(retriever=FakeRetriever([chunk(FACT)]), summarizer=FakeSummarizer(FACT, FACT),
                               factchecker=FakeFactchecker(["support"]), writer=writer) | options))


class ClaimContractTests(unittest.TestCase):
    def test_rejects_numbers_units_metric_fragments_and_missing_entities(self):
        for text in ("42", "42 participants", "210 ms", "92% accuracy", "Accuracy: 92%", "F1 = 0.92",
                     "Improved accuracy to 92%.", "Enrolled 42 participants.", "Was 42 participants.",
                     "After tuning, improved accuracy to 92%.", "It achieved 92% accuracy.",
                     "The sample 42 participants.", "The model is.", "Đã đạt độ chính xác 92%.",
                     "Sử dụng bốn mô hình.", "All achieved 92% accuracy.", "Tất cả đạt 92%."):
            with self.subTest(text=text):
                self.assertTrue(claim_contract_issues(text))

    def test_complete_qualitative_quantitative_passive_and_vietnamese_claims(self):
        for text in (FACT, "Model A achieved 92% accuracy.", "Model A reduced latency.",
                     "42 participants were enrolled.", "The model failed.", "Sources disagree.",
                     "The model did not improve recall.", "Model A had an F1 score of 0.92.",
                     "Mô hình A đạt độ chính xác 92%.", "Mô hình A sử dụng bốn lớp.",
                     "Nghiên cứu đã tuyển 42 người tham gia."):
            with self.subTest(text=text):
                self.assertEqual(claim_contract_issues(text), [])

    def test_every_sentence_checked_and_decimal_not_split(self):
        text = "Model A had an F1 score of 0.92. 42 participants."
        self.assertEqual(len(split_claims(text)), 2)
        self.assertEqual(claim_contract_issues(text)[0]["claim_index"], 1)
        self.assertEqual(claim_contract_issues("Model A reduced latency.\n- 42 participants.")[0]["claim_index"], 1)
        self.assertFalse(claim_contract_issues("- Model A reduced latency.\n- Model B improved recall."))
        self.assertEqual(claim_contract_issues(FACT + " improved accuracy to 92%.")[0]["claim_index"], 1)
        self.assertEqual(len(split_claims("Model A had a score of 0.92; 42 participants.")), 2)
        self.assertEqual(len(split_claims("Model A used features, e.g. embeddings.")), 1)

    def test_node_rewrites_before_verifier_even_if_critic_approves_fragment(self):
        node = SummarizerNode(None, None, None, None)
        node._call_generator = Mock(side_effect=[{"answer": "42 participants", "evidence_spans": [FACT]},
                                                {"answer": FACT, "evidence_spans": [FACT]}])
        node._call_critic = Mock(return_value=deepcopy(CRITIC))
        checker = FakeFactchecker(["support"])
        state = make_graph(retriever=FakeRetriever([chunk(FACT, "paper:orion")]), summarizer=node,
                           factchecker=checker, max_graph_retries=0).invoke({"question": "How many participants?"})
        self.assertEqual(node._call_generator.call_count, 2)
        self.assertEqual(node._call_critic.call_count, 2)
        self.assertIn("explicit entity", node._call_generator.call_args_list[1].args[2])
        self.assertEqual(checker.calls[0]["claim"], FACT)
        self.assertEqual(checker.calls[0]["context"], FACT)
        self.assertEqual(state["verified_claims"][0]["source_id"], "paper:orion")
        self.assertEqual(state["verified_claims"][0]["evidence"], FACT)
        trials = state["summary_diagnostics"]["trials"]
        self.assertEqual(trials[0]["action"], "rewrite")
        self.assertFalse(trials[0]["is_supported"])

    def test_rewrite_exhaustion_stays_within_existing_cap(self):
        for text in ("42", "42 participants", "Improved recall to 0.9."):
            with self.subTest(text=text):
                node = SummarizerNode(None, None, None, None)
                node._call_generator = Mock(return_value={"answer": text, "evidence_spans": [FACT]})
                node._call_critic = Mock(return_value=deepcopy(CRITIC))
                result = node.run(FACT, "Participants?")
                self.assertFalse(result.is_supported)
                self.assertEqual(result.confidence, "low")
                self.assertEqual(node._call_generator.call_count, config.MAX_INTERNAL_RETRY)
                self.assertEqual(node._call_critic.call_count, config.MAX_INTERNAL_RETRY)

    def test_missing_source_information_yields_without_inventing_a_subject(self):
        node = SummarizerNode(None, None, None, None)
        node._call_generator = Mock(return_value={"answer": "Unknown.", "evidence_spans": []})
        node._call_critic = Mock(return_value={"is_supported": False, "reason": "The study population is absent.",
                                             "action": "request_more_context", "suggested_query": "study population"})
        result = node.run("No relevant study details.", "How many participants?")
        self.assertFalse(result.is_supported)
        self.assertEqual(node._call_generator.call_count, 1)
        self.assertEqual(result.suggested_query, "study population")

    def test_graph_rejects_fragment_even_if_injected_summarizer_claims_high_confidence(self):
        for text in ("42", "42 participants", "Improved accuracy to 92%.", FACT + " 92% accuracy."):
            with self.subTest(text=text):
                checker = FakeFactchecker(["support"])
                state = make_graph(retriever=FakeRetriever([chunk(FACT)]),
                                   summarizer=FakeSummarizer(text, FACT), factchecker=checker,
                                   max_graph_retries=0).invoke({"question": "Participants?"})
                self.assertEqual(checker.calls, [])
                self.assertEqual(state["verified_claims"], [])
                self.assertIn("incomplete_claim_structure", state["summary_diagnostics"]["reasons"])

    def test_audit_evidence_fragments_never_reach_verifier_as_claims(self):
        checker = FakeFactchecker(["support"])
        summary = FakeSummarizer("Sources disagree.", FACT, supported=False)
        original = summary.run
        def run(**kwargs):
            result = original(**kwargs)
            result.evidence_spans = ["42 participants", "71 participants"]
            return result
        summary.run = run
        state = make_graph(retriever=FakeRetriever([chunk(FACT), chunk("The Orion study enrolled 71 participants.", "paper:other")]),
                           summarizer=summary, factchecker=checker, max_graph_retries=0).invoke({"question": "Participants?"})
        self.assertEqual(checker.calls, [])
        self.assertEqual(state["verified_claims"], [])
        self.assertIn("factchecker:incomplete_claim_structure", state["errors"])


if __name__ == "__main__":
    unittest.main()
