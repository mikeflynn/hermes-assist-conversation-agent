import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from bridge.hermes_api import HermesApiClient, HandoffResult, HermesApiError


class FakeHandler(BaseHTTPRequestHandler):
    calls = []
    mode = 'ok'
    caps = None
    def log_message(self, *args): pass
    def _reply(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        type(self).calls.append(('GET', self.path, self.headers.get('Authorization')))
        self._reply(200, type(self).caps or {'object':'hermes.api_server.capabilities','features':{'run_submission':True,'runs_idempotency':{'supported':True}},'endpoints':{'session_create':{'method':'POST','path':'/api/sessions'},'runs':{'method':'POST','path':'/v1/runs'}}})
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length',0)))
        type(self).calls.append(('POST',self.path,self.headers.get('Authorization'),self.headers.get('Idempotency-Key'),json.loads(body or b'{}')))
        if type(self).mode == 'http': return self._reply(500, {'error':'secret-ish'})
        if type(self).mode == 'malformed': return self._reply(202, {'object':'hermes.run'})
        if type(self).mode == 'conflict': return self._reply(409, {'error':'conflict'})
        if self.path == '/api/sessions': self._reply(201, {'object':'hermes.session','session':{'id':'sess-1'}})
        else: self._reply(202, {'run_id':'run-1','status':'queued','replayed':False})

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=HTTPServer(('127.0.0.1',0),FakeHandler); cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.thread.join()
    def setUp(self): FakeHandler.calls=[]; FakeHandler.mode='ok'; FakeHandler.caps=None; self.client=HermesApiClient('http://127.0.0.1:%d'%self.server.server_port,'test-secret',1)
    def test_authenticates_discovers_caps_and_creates_then_reuses_session(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d,'state.json'); self.assertEqual(self.client.get_capabilities()['object'],'hermes.api_server.capabilities')
            self.assertEqual(self.client.get_or_create_voice_session(p),'sess-1'); self.assertEqual(self.client.get_or_create_voice_session(p),'sess-1')
        self.assertTrue(all(c[2]=='Bearer test-secret' for c in FakeHandler.calls))
        self.assertEqual(sum(c[1]=='/api/sessions' for c in FakeHandler.calls),1)
    def test_submission_is_retry_safe_and_does_not_expose_key(self):
        r=self.client.submit_voice_request('sess-1','req-7','hello',{'source':'voice'})
        self.assertIsInstance(r,HandoffResult); self.assertEqual(r.status,'accepted'); self.assertEqual(r.session_id,'sess-1'); self.assertEqual(r.request_id,'req-7')
        call=FakeHandler.calls[-1]; self.assertEqual(call[3],'req-7'); self.assertEqual(call[4]['input'],'hello'); self.assertNotIn('test-secret',repr(r))
    def test_http_failure_is_typed_and_secret_safe(self):
        FakeHandler.mode='http'
        with self.assertRaises(HermesApiError) as cm: self.client.submit_voice_request('s','r','x',{})
        self.assertNotIn('test-secret',str(cm.exception))
    def test_duplicate_request_id_is_deduplicated_locally(self):
        self.client.submit_voice_request('s','same','x',{}); self.client.submit_voice_request('s','same','x',{})
        self.assertEqual(sum(c[1]=='/v1/runs' for c in FakeHandler.calls),2)

    def test_validates_capability_endpoint_and_feature_contract(self):
        FakeHandler.caps={'object':'hermes.api_server.capabilities','features':{'run_submission':True,'runs_idempotency':{'supported':True}},'endpoints':{'runs':{'method':'GET','path':'/wrong'}}}
        with self.assertRaises(HermesApiError): self.client.get_capabilities()

    def test_malformed_run_response_rejected(self):
        FakeHandler.mode='malformed'
        with self.assertRaises(HermesApiError): self.client.submit_voice_request('s','r','x',{})

    def test_server_conflict_fails_closed(self):
        FakeHandler.mode='conflict'
        with self.assertRaises(HermesApiError): self.client.submit_voice_request('s','r','x',{})

    def test_same_key_replay_sent_with_same_body_and_session_scoped(self):
        self.client.submit_voice_request('s1','same','x',{'a':1})
        self.client.submit_voice_request('s1','same','x',{'a':1})
        self.client.submit_voice_request('s2','same','x',{'a':1})
        calls=[c for c in FakeHandler.calls if c[1]=='/v1/runs']
        self.assertEqual(len(calls),3)
        self.assertTrue(all(c[4].get('input') == 'x' for c in calls))
        self.assertNotIn('context',calls[0][4])
        self.assertIn('instructions',calls[0][4])

    def test_retry_from_another_client_reaches_server_with_same_idempotency_key(self):
        self.client.submit_voice_request('s','cross-client','x',{})
        other=HermesApiClient('http://127.0.0.1:%d'%self.server.server_port,'test-secret',1)
        other.submit_voice_request('s','cross-client','x',{})
        calls=[c for c in FakeHandler.calls if c[1]=='/v1/runs']
        self.assertEqual(len(calls),2)
        self.assertEqual([c[3] for c in calls],['cross-client','cross-client'])

    def test_changed_payload_same_key_fails_closed(self):
        self.client.submit_voice_request('s','same','x',{'a':1})
        FakeHandler.mode='conflict'
        with self.assertRaises(HermesApiError): self.client.submit_voice_request('s','same','different',{'a':2})

    def test_timeout_is_typed(self):
        client=HermesApiClient('http://10.255.255.1','secret',0.001)
        with self.assertRaises(HermesApiError): client.get_capabilities()

if __name__=='__main__': unittest.main()
