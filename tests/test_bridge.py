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
        for policy in (VoicePolicy((unknown,)),):
            result = bridge.route_voice_request('please research this', client, policy, '', '')
            self.assertEqual(result.status, 'unsupported')
        client.get_or_create_voice_session.assert_not_called()

    def test_api_unavailable_does_not_claim_handoff(self):
        result = bridge.route_voice_request('please research this', None, VoicePolicy(()), '', '')
        self.assertNotEqual(result.status, 'handed_off')

    def test_injected_authorized_client_confirms_handoff(self):
        policy = VoicePolicy((CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.get_or_create_voice_session.return_value = 'safe-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='safe-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('please research this', client, policy, '', '', 'safe-request')
        self.assertEqual(result.status, 'handed_off')
        self.assertEqual(result.session_id, 'safe-session')

    def test_registered_home_assistant_and_conduit_tools_match_live_inventory(self):
        homeassistant = ('ha_call_service', 'ha_get_state', 'ha_list_entities', 'ha_list_services')
        conduit = ('conduit_call_user', 'conduit_call_watch', 'conduit_settings', 'conduit_watch_report')
        policy = VoicePolicy((
            CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),
            CapabilityRegistration('home_assistant', 'Home Assistant tools approved for voice', homeassistant, 'direct_tool_access', (), True),
            CapabilityRegistration('conduit', 'Conduit tools approved for voice', conduit, 'direct_tool_access', (), True),
        ))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset(homeassistant + conduit)
        client.get_or_create_voice_session.return_value = 'voice-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='voice-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('please check my home', client, policy, '', '', 'approved-tools')
        self.assertEqual(result.status, 'handed_off')
        self.assertEqual(result.session_id, 'voice-session')
        client.submit_voice_request.assert_called_once()

    def test_empty_registry_allows_no_tool_transport_only_when_inventory_matches(self):
        client = Mock()
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.get_capabilities.return_value = {'ok': True}
        client.get_or_create_voice_session.return_value = 'safe-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='safe-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('please research this', client, VoicePolicy(()), '', '', 'empty-registry-safe')
        self.assertEqual(result.status, 'handed_off')
        client.submit_voice_request.assert_called_once()

    def test_tool_inventory_mismatch_prevents_run(self):
        policy = VoicePolicy((CapabilityRegistration('x', 'x', ('allowed_tool',), 'read_only', (), True),))
        client = Mock()
        client.get_enabled_tool_inventory.return_value = frozenset(('unregistered_tool',))
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('please research this', client, policy, '', '', 'inventory-mismatch')
        self.assertNotEqual(result.status, 'handed_off')
        client.submit_voice_request.assert_not_called()

    def test_identical_text_new_history_gets_distinct_request_identity(self):
        first = bridge.derive_request_id('conversation', 'same question', 'Earlier: one')
        second = bridge.derive_request_id('conversation', 'same question', 'Earlier: two')
        self.assertNotEqual(first, second)

    def test_cached_handoff_isolated_by_state_identity(self):
        client = Mock()
        client.get_or_create_voice_session.side_effect = ['sess-a', 'sess-b']
        client.submit_voice_request.side_effect = [Mock(status='accepted', session_id='sess-a'), Mock(status='accepted', session_id='sess-b')]
        bridge._HANDOFF_CACHE.clear()
        a = bridge.handoff_request(client, 'state-a', 'same-id', 'same text', '')
        b = bridge.handoff_request(client, 'state-b', 'same-id', 'same text', '')
        self.assertEqual(a.session_id, 'sess-a')
        self.assertEqual(b.session_id, 'sess-b')
        self.assertEqual(client.submit_voice_request.call_count, 2)

    def test_actual_submit_sends_current_text_separately_from_trimmed_context(self):
        client = Mock()
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.get_capabilities.return_value = {'ok': True}
        client.get_or_create_voice_session.return_value = 'sess-context'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='sess-context')
        bridge._HANDOFF_CACHE.clear()
        bridge.route_voice_request('current utterance', client, VoicePolicy(()), '', '', 'context-current', 'old history')
        args = client.submit_voice_request.call_args[0]
        self.assertEqual(args[2], 'current utterance')
        self.assertIn('current utterance', args[3]['history'])

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
        client.submit_voice_request.side_effect = [Mock(status='failed', session_id='sess'), Mock(status='accepted', session_id='sess')]
        bridge._HANDOFF_CACHE.clear()
        result = bridge.handoff_request(client, 'state', 'req-fail', 'please research', '')
        self.assertEqual(result.status, 'unavailable')
        retried = bridge.handoff_request(client, 'state', 'req-fail', 'please research', '')
        self.assertEqual(retried.status, 'handed_off')
        self.assertEqual(client.submit_voice_request.call_count, 2)

if __name__ == '__main__': unittest.main()
