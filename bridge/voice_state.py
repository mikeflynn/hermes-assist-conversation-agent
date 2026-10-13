"""Private, atomic persistence for the dedicated voice session."""
import json
import os
import tempfile
import threading
import fcntl

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

    def remember_request(self, session_id, request_id, fingerprint):
        """Persist request identity under its session; server remains dedupe authority."""
        with self._lock:
            lock_path=self.path+'.lock'
            directory=os.path.dirname(os.path.abspath(lock_path)); os.makedirs(directory,exist_ok=True)
            fd=os.open(lock_path,os.O_CREAT|os.O_RDWR,0o600)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX)
                data=self._read(); records=data.get('requests',[])
                if not isinstance(records,list): records=[]
                record={'session_id':session_id,'request_id':request_id,'fingerprint':fingerprint}
                if record not in records: records.append(record)
                data['requests']=records[-self.recent_limit:]
                data['session_id']=session_id
                data['request_ids']=[r.get('request_id') for r in data['requests'] if r.get('session_id')==session_id]
                self._write(data)
            finally:
                fcntl.flock(fd,fcntl.LOCK_UN); os.close(fd)
