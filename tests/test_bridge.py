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
            result = bridge.route_voice_request('Please send this to my Voice Requests session: research this.', client, policy, '', '')
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
        result = bridge.route_voice_request('Please send this to Voice Requests: research this.', client, policy, '', '', 'safe-request')
        self.assertEqual(result.status, 'handed_off')
        self.assertEqual(result.session_id, 'safe-session')

    def test_quick_home_assistant_state_question_returns_spoken_answer_without_handoff(self):
        tools = frozenset(('ha_call_service', 'ha_get_state', 'ha_list_entities', 'ha_list_services', 'conduit_call_user', 'conduit_call_watch', 'conduit_settings', 'conduit_watch_report'))
        policy = VoicePolicy((
            CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),
            CapabilityRegistration('home_assistant', 'Home Assistant tools', ('ha_call_service', 'ha_get_state', 'ha_list_entities', 'ha_list_services'), 'direct_tool_access', (), True),
            CapabilityRegistration('conduit', 'Conduit tools', ('conduit_call_user', 'conduit_call_watch', 'conduit_settings', 'conduit_watch_report'), 'direct_tool_access', (), True),
        ))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = tools
        client.answer_voice_request.return_value = 'The lights are on in the boy’s room.'
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Are the lights on in the boy’s room?', client, policy, '', '', 'quick-room-state')
        self.assertEqual(result.status, 'answered')
        self.assertEqual(result.spoken_reply, 'The lights are on in the boy’s room.')
        client.answer_voice_request.assert_called_once()
        client.get_or_create_voice_session.assert_not_called()
        client.submit_voice_request.assert_not_called()

    def test_clear_home_assistant_command_gets_inline_spoken_result(self):
        tools = frozenset(('ha_call_service', 'ha_get_state', 'ha_list_entities', 'ha_list_services', 'conduit_call_user', 'conduit_call_watch', 'conduit_settings', 'conduit_watch_report'))
        policy = VoicePolicy((
            CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),
            CapabilityRegistration('home_assistant', 'Home Assistant tools', ('ha_call_service', 'ha_get_state', 'ha_list_entities', 'ha_list_services'), 'direct_tool_access', (), True),
            CapabilityRegistration('conduit', 'Conduit tools', ('conduit_call_user', 'conduit_call_watch', 'conduit_settings', 'conduit_watch_report'), 'direct_tool_access', (), True),
        ))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = tools
        client.answer_voice_request.return_value = 'Done. The hallway lights are off.'
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Turn off the hallway lights.', client, policy, '', '', 'direct-light-control')
        self.assertEqual(result.status, 'answered')
        self.assertEqual(result.spoken_reply, 'Done. The hallway lights are off.')
        client.answer_voice_request.assert_called_once()
        client.submit_voice_request.assert_not_called()
        client.get_or_create_voice_session.assert_not_called()

    def test_unconfirmed_destructive_action_is_routed_to_voice_requests(self):
        policy = VoicePolicy((CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.get_or_create_voice_session.return_value = 'voice-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='voice-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Delete the old note.', client, policy, '', '', 'delete-action')
        self.assertEqual(result.status, 'handed_off')
        client.submit_voice_request.assert_called_once()
        client.answer_voice_request.assert_not_called()

    def test_explicit_voice_requests_destination_hands_off_instead_of_answering_inline(self):
        policy = VoicePolicy((CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.get_or_create_voice_session.return_value = 'voice-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='voice-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Please send this answer to my Voice Requests session: are the lights on?', client, policy, '', '', 'explicit-voice-session')
        self.assertEqual(result.status, 'handed_off')
        client.submit_voice_request.assert_called_once()
        client.answer_voice_request.assert_not_called()

    def test_confirmation_request_hands_off_before_inline_execution(self):
        policy = VoicePolicy((CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.get_or_create_voice_session.return_value = 'voice-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='voice-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Delete the old note, but ask me for confirmation first.', client, policy, '', '', 'confirmation-required')
        self.assertEqual(result.status, 'handed_off')
        client.submit_voice_request.assert_called_once()
        client.answer_voice_request.assert_not_called()

    def test_model_confirmation_marker_hands_off_instead_of_speaking_marker(self):
        policy = VoicePolicy((CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.answer_voice_request.return_value = 'HANDOFF_REQUIRED: This request needs your approval.'
        client.get_or_create_voice_session.return_value = 'voice-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='voice-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Please change the smart-home setup.', client, policy, '', '', 'model-marker')
        self.assertEqual(result.status, 'handed_off')
        self.assertNotIn('HANDOFF_REQUIRED', result.spoken_reply)
        client.answer_voice_request.assert_called_once()
        client.submit_voice_request.assert_called_once()

    def test_informational_email_statement_stays_inline(self):
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.answer_voice_request.return_value = 'Email is not secure enough for that use.'
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Email is not secure enough for that use.', client, VoicePolicy(()), '', '', 'email-fact')
        self.assertEqual(result.status, 'answered')
        client.answer_voice_request.assert_called_once()
        client.submit_voice_request.assert_not_called()

    def test_inline_failure_does_not_claim_nothing_happened(self):
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.answer_voice_request.side_effect = TimeoutError('timed out')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Turn off the hallway lights.', client, VoicePolicy(()), '', '', 'inline-timeout')
        self.assertEqual(result.status, 'unavailable')
        self.assertIn("can't confirm", result.spoken_reply)
        client.submit_voice_request.assert_not_called()

    def test_current_sports_question_uses_inline_web_search(self):
        policy = VoicePolicy((CapabilityRegistration('web_search', 'Read-only web lookup', ('web_search', 'web_extract'), 'read_only', (), True),))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset({'web_search', 'web_extract'})
        client.answer_voice_request.return_value = 'The Lakers won 112 to 108.'
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('What was the Lakers score last night?', client, policy, '', '', 'sports-score')
        self.assertEqual(result.status, 'answered')
        self.assertEqual(result.spoken_reply, 'The Lakers won 112 to 108.')
        instructions = client.answer_voice_request.call_args.kwargs['instructions']
        self.assertIn('web_search', instructions)
        self.assertIn('current or time-sensitive', instructions)
        self.assertIn('source', instructions.lower())
        self.assertIn('timezone', instructions.lower())
        self.assertIn('do not infer or shift calendar dates', instructions.lower())
        client.submit_voice_request.assert_not_called()

    def test_non_confirmation_research_question_gets_inline_answer(self):
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset()
        client.answer_voice_request.return_value = 'Here is the concise summary.'
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Please research this and give me a concise summary.', client, VoicePolicy(()), '', '', 'inline-research')
        self.assertEqual(result.status, 'answered')
        self.assertEqual(result.spoken_reply, 'Here is the concise summary.')
        client.submit_voice_request.assert_not_called()

    def test_registered_home_assistant_conduit_and_web_tools_match_live_inventory(self):
        homeassistant = ('ha_call_service', 'ha_get_state', 'ha_list_entities', 'ha_list_services')
        conduit = ('conduit_call_user', 'conduit_call_watch', 'conduit_settings', 'conduit_watch_report')
        web = ('web_search', 'web_extract')
        policy = VoicePolicy((
            CapabilityRegistration('voice_handoff', 'handoff', ('hermes_api',), 'proposal_only', (), True),
            CapabilityRegistration('home_assistant', 'Home Assistant tools approved for voice', homeassistant, 'direct_tool_access', (), True),
            CapabilityRegistration('conduit', 'Conduit tools approved for voice', conduit, 'direct_tool_access', (), True),
            CapabilityRegistration('web_search', 'Read-only web search', web, 'read_only', (), True),
        ))
        client = Mock()
        client.get_capabilities.return_value = {'ok': True}
        client.get_enabled_tool_inventory.return_value = frozenset(homeassistant + conduit + web)
        client.get_or_create_voice_session.return_value = 'voice-session'
        client.submit_voice_request.return_value = Mock(status='accepted', session_id='voice-session')
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Please send this to Voice Requests: check my home.', client, policy, '', '', 'approved-tools')
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
        result = bridge.route_voice_request('Please send this to Voice Requests: research this.', client, VoicePolicy(()), '', '', 'empty-registry-safe')
        self.assertEqual(result.status, 'handed_off')
        client.submit_voice_request.assert_called_once()

    def test_tool_inventory_mismatch_prevents_run(self):
        policy = VoicePolicy((CapabilityRegistration('x', 'x', ('allowed_tool',), 'read_only', (), True),))
        client = Mock()
        client.get_enabled_tool_inventory.return_value = frozenset(('unregistered_tool',))
        bridge._HANDOFF_CACHE.clear()
        result = bridge.route_voice_request('Please send this to Voice Requests: research this.', client, policy, '', '', 'inventory-mismatch')
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
        bridge.route_voice_request('Please send this to Voice Requests: current utterance.', client, VoicePolicy(()), '', '', 'context-current', 'old history')
        args = client.submit_voice_request.call_args[0]
        self.assertEqual(args[2], 'Please send this to Voice Requests: current utterance.')
        self.assertIn('current utterance', args[3]['history'])

    def test_inline_chat_history_preserves_roles_and_excludes_current_turn(self):
        data = {'chat_log': {'content': [
            {'role': 'user', 'content': 'Earlier question'},
            {'role': 'assistant', 'content': [{'text': 'Earlier answer'}]},
            {'role': 'user', 'content': 'Current question'},
        ]}}
        self.assertEqual(bridge.format_chat_history(data, 'Current question'), [
            {'role': 'user', 'content': 'Earlier question'},
            {'role': 'assistant', 'content': 'Earlier answer'},
        ])

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
