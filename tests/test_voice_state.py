import json
import os
import stat
import tempfile
import unittest
from bridge.voice_state import VoiceState

class VoiceStateTests(unittest.TestCase):
    def test_atomic_private_state_roundtrip_and_recent_request_ids(self):
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d,'state.json')
            state=VoiceState(p)
            state.save_session('s-1')
            state.remember_request('s-1','r-1','fingerprint')
            self.assertEqual(state.load_session(),'s-1')
            self.assertIn('r-1',state.recent_request_ids())
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode),0o600)
    def test_missing_state_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            state=VoiceState(os.path.join(d,'missing.json'))
            self.assertIsNone(state.load_session())
            self.assertEqual(state.recent_request_ids(),[])

if __name__=='__main__': unittest.main()
