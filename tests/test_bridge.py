import unittest
from unittest.mock import Mock
from bridge import bridge

class BridgeOutcomeTests(unittest.TestCase):
    def test_history_trimming_keeps_current_utterance(self):
        old = bridge.MAX_HISTORY_MESSAGES
        bridge.MAX_HISTORY_MESSAGES = 1
        try:
            data = {'chat_log': {'content': [{'role':'user','content':'old '*400}, {'role':'assistant','content':'reply'}, {'role':'user','content':'current question'}]}}
            history = bridge.format_history(data, 'current question')
            self.assertIn('old', history)
            self.assertNotIn('current question', history)
            prompt = bridge.build_voice_context('current question', history)
            self.assertIn('current question', prompt)
        finally:
            bridge.MAX_HISTORY_MESSAGES = old

    def test_duplicate_request_reuses_same_handoff(self):
        client = Mock()
        client.get_or_create_voice_session.return_value = 'sess'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='sess')
        bridge._HANDOFF_CACHE.clear()
        first = bridge.handoff_request(client, 'state', 'req-id', 'please research', '')
        second = bridge.handoff_request(client, 'state', 'req-id', 'please research', '')
        self.assertEqual(first.status, 'handed_off')
        self.assertEqual(second.status, 'handed_off')
        client.submit_voice_request.assert_called_once()

    def test_failed_handoff_is_not_reported_as_success(self):
        client = Mock()
        client.get_or_create_voice_session.return_value = 'sess'
        client.submit_voice_request.return_value = Mock(status='failed', session_id='sess')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.handoff_request(client, 'state', 'req-fail', 'please research', '')
        self.assertEqual(result.status, 'unavailable')

if __name__ == '__main__': unittest.main()
