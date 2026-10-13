"""Small authenticated client for the Hermes API Server."""
import json
import urllib.error
import urllib.request

from .voice_state import VoiceState

MAX_RESPONSE = 1024 * 1024
MAX_REQUEST = 256 * 1024

class HermesApiError(Exception):
    pass

class HandoffResult:
    def __init__(self, status, session_id, request_id, detail=None):
        self.status=status; self.session_id=session_id; self.request_id=request_id; self.detail=detail
    def __repr__(self):
        return 'HandoffResult(status={!r}, session_id={!r}, request_id={!r}, detail={!r})'.format(self.status,self.session_id,self.request_id,self.detail)

class HermesApiClient:
    def __init__(self, base_url, api_key, timeout=10):
        if not isinstance(api_key,str) or not api_key: raise ValueError('API key required')
        self.base_url=base_url.rstrip('/')
        self._api_key=api_key
        self.timeout=timeout
        self._submitted = {}
        self._voice_state = None

    def _request(self, method, path, payload=None, idempotency_key=None):
        data=None
        headers={'Authorization':'Bearer '+self._api_key,'Accept':'application/json'}
        if payload is not None:
            data=json.dumps(payload,separators=(',',':')).encode('utf-8')
            if len(data)>MAX_REQUEST: raise HermesApiError('request too large')
            headers['Content-Type']='application/json'
        if idempotency_key: headers['Idempotency-Key']=idempotency_key
        req=urllib.request.Request(self.base_url+path,data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=self.timeout) as response:
                raw=response.read(MAX_RESPONSE+1)
        except urllib.error.HTTPError as e:
            raise HermesApiError('Hermes API returned HTTP {}'.format(e.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason=getattr(e,'reason',None)
            if isinstance(reason,TimeoutError) or isinstance(e,TimeoutError): raise HermesApiError('Hermes API request timed out') from None
            raise HermesApiError('Hermes API request failed') from None
        if len(raw)>MAX_RESPONSE: raise HermesApiError('response too large')
        try: result=json.loads(raw.decode('utf-8'))
        except (ValueError,UnicodeError): raise HermesApiError('malformed JSON response') from None
        if not isinstance(result,dict): raise HermesApiError('malformed API response')
        return result

    def get_capabilities(self):
        data=self._request('GET','/v1/capabilities')
        if data.get('object')!='hermes.api_server.capabilities' or not isinstance(data.get('features'),dict) or not isinstance(data.get('endpoints'),dict):
            raise HermesApiError('invalid capabilities response')
        return data

    def get_or_create_voice_session(self, state_path):
        state=VoiceState(state_path)
        self._voice_state=state
        existing=state.load_session()
        if existing: return existing
        response=self._request('POST','/api/sessions',{'title':'Voice Requests'})
        session=response.get('session')
        sid=session.get('id') if isinstance(session,dict) else None
        if response.get('object')!='hermes.session' or not isinstance(sid,str) or not sid: raise HermesApiError('invalid session response')
        state.save_session(sid)
        return sid

    def submit_voice_request(self, session_id, request_id, text, context):
        if not all(isinstance(x,str) and x for x in (session_id,request_id,text)): raise HermesApiError('invalid handoff request')
        if self._voice_state is not None and request_id in self._voice_state.recent_request_ids():
            return HandoffResult('accepted',session_id,request_id,'deduplicated')
        prior=self._submitted.get((session_id,request_id))
        if prior is not None: return prior
        response=self._request('POST','/v1/runs',{'input':text,'session_id':session_id,'context':context},request_id)
        run=response.get('run')
        run_id=run.get('id') if isinstance(run,dict) else None
        status=run.get('status') if isinstance(run,dict) else None
        if response.get('object')!='hermes.run' or not isinstance(run_id,str) or not run_id or not isinstance(status,str): raise HermesApiError('invalid run response')
        result=HandoffResult('accepted',session_id,request_id,status)
        self._submitted[(session_id,request_id)]=result
        if self._voice_state is not None: self._voice_state.remember_request(request_id)
        return result
