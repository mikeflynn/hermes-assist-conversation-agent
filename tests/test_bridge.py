import unittest
from unittest.mock import Mock
from bridge import bridge
from bridge.voice_policy import VoicePolicy, CapabilityRegistration
from pathlib import Path
from tempfile import TemporaryDirectory

class BridgeOutcomeTests(unittest.TestCase):
    def test_cached_calendar_and_things_requests_do_not_call_api(self):
        with TemporaryDirectory() as directory:
            calendar = Path(directory) / 'calendar.md'
            things = Path(directory) / 'things.md'
            news = Path(directory) / 'news.md'
            calendar.write_text('Calendar cache content')
            things.write_text('Things cache content')
            news.write_text('News cache content')
            client = Mock()
            self.assertEqual(bridge.route_voice_request('What is on my calendar today?', client, VoicePolicy(()), str(calendar), str(things), news_path=str(news)).spoken_reply, 'Calendar cache content')
            self.assertEqual(bridge.route_voice_request('What do I need to do today?', client, VoicePolicy(()), str(calendar), str(things), news_path=str(news)).spoken_reply, 'Things cache content')
            self.assertEqual(bridge.route_voice_request('Give me the news', client, VoicePolicy(()), str(calendar), str(things), news_path=str(news)).spoken_reply, 'News cache content')
            client.assert_not_called()

    def test_empty_or_unknown_policy_denies_api_handoff(self):
        client = Mock()
        unknown = CapabilityRegistration('other_capability', 'other', ('different_tool',), 'read_only', (), True)
        for policy in (VoicePolicy(()), VoicePolicy((unknown,))):
            result = bridge.route_voice_request('please research this', client, policy, '', '')
            self.assertEqual(result.status, 'unsupported')
        client.get_or_create_voice_session.assert_not_called()

    def test_api_unavailable_does_not_claim_handoff(self):
        result = bridge.route_voice_request('please research this', None, VoicePolicy(()), '', '')
        self.assertNotEqual(result.status, 'handed_off')

    def test_injected_authorized_client_confirms_handoff(self):
        policy = VoicePolicy((CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),))
        client = Mock()
        client.get_or_create_voice_session.return_value = 'safe-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='safe-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('please research this', client, policy, '', '', 'safe-request')
        self.assertEqual(result.status, 'handed_off')
        self.assertEqual(result.session_id, 'safe-session')

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
