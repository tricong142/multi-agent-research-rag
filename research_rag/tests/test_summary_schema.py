"""Malformed model contracts must fail closed and stay inside the retry cap."""
from copy import deepcopy
import unittest
from unittest.mock import Mock

from train_agent3_summarizer import config
from train_agent3_summarizer.node import SummarizerNode


GENERATOR = {'answer': 'The report evaluated four models.',
             'evidence_spans': ['The report evaluated four models.']}
CRITIC = {'is_supported': True, 'reason': 'Direct evidence.', 'action': ''}


class SummarySchemaTests(unittest.TestCase):
    def node(self, outputs):
        node = SummarizerNode(None, None, None, None)
        node._generate_json = Mock(side_effect=deepcopy(outputs))
        return node

    def test_generator_bad_schema_repairs_before_critic_and_does_not_crash(self):
        for bad in ([], {}, None, {'answer': 'Missing spans'},
                    {**GENERATOR, 'answer': 4}, {**GENERATOR, 'evidence_spans': 'source'},
                    {**GENERATOR, 'evidence_spans': [None]}):
            with self.subTest(bad=bad):
                node = self.node([bad, GENERATOR, CRITIC])
                result = node.run(GENERATOR['answer'], 'What was evaluated?')
                self.assertTrue(result.is_supported)
                self.assertEqual(len(result.reasoning_trace), 2)
                calls = node._generate_json.call_args_list
                self.assertEqual([c.kwargs['role'] for c in calls], ['generator', 'generator', 'critic'])
                self.assertIn('JSON/schema invalid', calls[1].args[3])

    def test_generator_exhaustion_cannot_be_approved_by_critic(self):
        node = self.node([[]] * config.MAX_INTERNAL_RETRY)
        result = node.run('Source.', 'Question?')
        self.assertFalse(result.is_supported)
        self.assertEqual(result.confidence, 'low')
        self.assertEqual(node._generate_json.call_count, config.MAX_INTERNAL_RETRY)
        self.assertTrue(all(c.kwargs['role'] == 'generator' for c in node._generate_json.call_args_list))

    def test_critic_bad_schema_cannot_support_and_repairs_with_finite_budget(self):
        for bad in ([], {}, {'is_supported': True}, {**CRITIC, 'is_supported': 'true'},
                    {**CRITIC, 'reason': None}, {**CRITIC, 'action': []},
                    {**CRITIC, 'suggested_query': 4}):
            with self.subTest(bad=bad):
                node = self.node([GENERATOR, bad] * config.MAX_INTERNAL_RETRY)
                result = node.run(GENERATOR['answer'], 'What was evaluated?')
                self.assertFalse(result.is_supported)
                self.assertEqual(len(result.reasoning_trace), config.MAX_INTERNAL_RETRY)
                self.assertEqual(node._generate_json.call_count, 2 * config.MAX_INTERNAL_RETRY)
                self.assertIn('Critic JSON/schema invalid', result.missing_information[0])


if __name__ == '__main__':
    unittest.main()
