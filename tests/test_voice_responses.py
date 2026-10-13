import unittest
from bridge.voice_responses import VoiceOutcome, format_spoken_reply

class VoiceResponseTests(unittest.TestCase):
    def test_formats_all_outcomes(self):
        cases = {
            'answered': 'The answer is ready.',
            'handed_off': 'I sent that to your Voice Requests session.',
            'unsupported': "I can't do that from the voice assistant. I haven't taken action.",
            'unavailable': "I couldn't send that to Hermes, so nothing was started.",
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                self.assertEqual(format_spoken_reply(VoiceOutcome(status, expected)), expected)

    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            VoiceOutcome('maybe', 'unknown')

if __name__ == '__main__': unittest.main()
