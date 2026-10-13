"""Private, atomic persistence for the dedicated voice session."""
import json
import os
import tempfile
import threading

class VoiceState:
    def __init__(self, path, recent_limit=100):
        self.path = os.fspath(path)
        self.recent_limit = recent_limit
        self._lock = threading.RLock()

    def _read(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data=json.load(f)
            if not isinstance(data,dict): return {}
            return data
        except FileNotFoundError:
            return {}

    def _write(self, data):
        directory=os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.voice-state-', dir=directory)
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump(data,f,separators=(',',':'))
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp,self.path)
            try: os.chmod(self.path,0o600)
            except OSError: pass
        finally:
            try: os.unlink(tmp)
            except FileNotFoundError: pass

    def load_session(self):
        with self._lock:
            value=self._read().get('session_id')
            return value if isinstance(value,str) and value else None

    def save_session(self, session_id):
        if not isinstance(session_id,str) or not session_id: raise ValueError('invalid session id')
        with self._lock:
            data=self._read(); data['session_id']=session_id; data.setdefault('request_ids',[]); self._write(data)

    def recent_request_ids(self):
        with self._lock:
            ids=self._read().get('request_ids',[])
            return ids[-self.recent_limit:] if isinstance(ids,list) else []

    def remember_request(self, request_id):
        with self._lock:
            data=self._read(); ids=data.get('request_ids',[])
            if not isinstance(ids,list): ids=[]
            if request_id not in ids: ids.append(request_id)
            data['request_ids']=ids[-self.recent_limit:]; data.setdefault('session_id',None); self._write(data)
