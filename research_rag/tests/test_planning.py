"""Synthetic contract/regression tests; these do not measure real model quality."""
import unittest
from types import SimpleNamespace

from research_rag.planning import ResearchPlan, create_plan
from research_rag.retrieval import RetrievalAgent
from research_rag.tests.test_autonomy import make_graph
from research_rag.tests.test_integration import FakeRetriever, chunk


A = "Alpha uses sparse lexical matching."
B = "Beta uses dense semantic matching."


class TaskSummarizer:
    def run(self, context, question):
        answer = A if question.startswith("Evidence about Alpha") else B if question.startswith("Evidence about Beta") else A + " " + B
        spans = [s for s in (A, B) if s in answer]
        supported = all(s in context for s in spans)
        return SimpleNamespace(answer=answer, evidence_spans=spans if supported else [],
                               is_supported=supported, confidence="high" if supported else "low",
                               missing_information=[] if supported else ["Missing Beta evidence"],
                               suggested_query=None if supported else "Beta semantic matching")


class PlanningTests(unittest.TestCase):
    def test_comparison_decomposes_and_waits_for_both_methods(self):
        class Retriever(FakeRetriever):
            def search(self, *args, **kwargs):
                result = super().search(*args, **kwargs)
                result["chunks"] = [chunk(A, "alpha")] if len(self.calls) == 1 else [chunk(B, "beta")]
                return result
        result = make_graph(retriever=Retriever([]), summarizer=TaskSummarizer()).invoke({"question": "Compare Alpha and Beta."})
        tasks = result["research_plan"]["tasks"]
        self.assertEqual([t["status"] for t in tasks], ["complete"] * 3)
        self.assertEqual(tasks[-1]["depends_on"], ["t1", "t2"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["search_count"], 2)
        self.assertEqual([c["task_id"] for c in result["agent_cycles"] if c["agent"] == "summarize"], ["t1", "t2", "synthesis"])
        self.assertEqual(result["agent_cycles"][-1]["agent"], "write")

    def test_one_sided_comparison_cannot_complete_or_invoke_writer(self):
        result = make_graph(retriever=FakeRetriever([chunk(A)]), summarizer=TaskSummarizer()).invoke({"question": "Compare Alpha and Beta."})
        self.assertNotEqual(result["status"], "completed")
        self.assertNotIn("write", [h["action"] for h in result["action_history"]])
        self.assertEqual(result["research_plan"]["tasks"][0]["status"], "complete")
        self.assertNotEqual(result["research_plan"]["tasks"][1]["status"], "complete")

    def test_new_source_rechecks_old_task_claims_and_preserves_conflict(self):
        class Retriever(FakeRetriever):
            def search(self, *args, **kwargs):
                result = super().search(*args, **kwargs)
                result["chunks"] = [chunk(A, "alpha")] if len(self.calls) == 1 else [chunk(B + " Alpha does not use sparse matching.", "beta")]
                return result
        calls = []
        def checker(state):
            calls.append(state)
            label = "contradict" if state["claim"] == A and "does not" in state["context"] else "support"
            return {"fact_check_label": label, "confidence_score": .9, "fact_check_status": "ok"}
        result = make_graph(retriever=Retriever([]), summarizer=TaskSummarizer(), factchecker=checker).invoke({"question": "Compare Alpha and Beta."})
        self.assertTrue(any(c["claim"] == A and "does not" in c["context"] for c in calls))
        self.assertNotIn(A, [c["text"] for c in result["verified_claims"]])
        self.assertNotEqual(result["status"], "completed")

    def test_missing_information_revises_plan_and_nodes_are_distinct(self):
        graph = make_graph(retriever=FakeRetriever([chunk(A)]), summarizer=TaskSummarizer(), max_graph_retries=2)
        self.assertTrue({"reader", "retrieval", "summarizer", "factchecker", "writer"} <= graph.get_graph().nodes.keys())
        self.assertNotIn("execute", graph.get_graph().nodes)
        result = graph.invoke({"question": "Compare Alpha and Beta."})
        self.assertTrue(any(h["event"] == "revise" for h in result["plan_history"]))
        self.assertTrue(result["research_plan"]["tasks"][1]["missing_questions"])

    def test_plan_rejects_cycles_and_distrusts_provided_completions(self):
        with self.assertRaises(ValueError):
            ResearchPlan.model_validate({"tasks": [{"task_id": "t1", "question": "Q", "depends_on": ["t1"]}]})
        plan = create_plan("Q", {"tasks": [{"task_id": "t1", "question": "Q", "status": "complete", "claim_texts": ["invented"]}]})
        self.assertEqual(plan["tasks"][0]["status"], "pending")
        self.assertEqual(plan["tasks"][0]["claim_texts"], [])

    def test_retrieval_agent_changes_query_and_tool_from_feedback(self):
        service = FakeRetriever([chunk(B)])
        agent = RetrievalAgent(service)
        state = {"question": "Which method?", "active_task_id": "t1", "active_query": "method",
                 "research_plan": create_plan("Which method?"), "agent_result": {},
                 "retrieval_history": [], "search_count": 0, "budget": {"max_searches": 3}}
        first = agent.run(state=state, top_k=1)
        self.assertEqual(first["requested_method"], "bm25")
        state["retrieval_history"] = [{"task_id": "t1", "query": first["query"], "requested_method": "bm25", "tool": "bm25", "top_k": 1, "has_hits": True}]
        state["agent_result"] = {"suggested_query": "Beta dense matching", "missing_information": ["Beta evidence"]}
        second = agent.run(state=state, top_k=2)
        self.assertEqual(service.calls[-1]["query"], "Beta dense matching")
        self.assertEqual(service.calls[-1]["method"], "dense")
        self.assertEqual(second["trace"][0]["actual_tool"], "bm25")  # fake reports actual BM25 truthfully
        self.assertFalse(second["trace"][0]["evaluation"]["relevance_verified"])


if __name__ == "__main__":
    unittest.main()
