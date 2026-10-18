from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceOutcome:
    status: str
    spoken_reply: str
    request_id: str = None
    session_id: str = None

    def __post_init__(self):
        if self.status not in {'answered', 'handed_off', 'unsupported', 'unavailable'}:
            raise ValueError('invalid voice outcome status')


def format_spoken_reply(outcome):
    return outcome.spoken_reply
