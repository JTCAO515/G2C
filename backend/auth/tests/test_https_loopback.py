"""Opt-in 127.0.0.1 TLS tests; temporary synthetic CA, never installed in system trust."""
import datetime, ipaddress, json, os, socket, ssl, tempfile, threading, time, unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
from cj_auth.https_jwks_transport import HTTPSConfiguration,HTTPSJWKSTransport,HTTPTransportFailure
from cj_auth.jwks_provider import JWKSConfiguration,JWKSRequest,BoundedJWKSProvider
from cj_auth.jwt_adapter import JWTConfiguration,PyJWTVerifier
from cj_auth.interfaces import VerificationStatus


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args): pass
    def do_GET(self):
        with self.server.condition:
            self.server.active+=1;self.server.paths.append(self.path)
        try:
            if self.path=='/redirect':
                self.send_response(302);self.send_header('Location',self.server.url+'/target')
                self.send_header('Content-Length','0');self.end_headers();return
            data=self.server.document
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.server.headers_sent.set()
            if self.path=='/stall': self.server.release.wait(2)
            if self.path=='/drip':
                for byte in data:
                    self.wfile.write(bytes([byte]));self.wfile.flush()
                    if self.server.release.wait(.03): break
            else: self.wfile.write(data);self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,ssl.SSLError): pass
        finally:
            with self.server.condition:
                self.server.active-=1;self.server.condition.notify_all()


@unittest.skipUnless(os.environ.get('CJ_AUTH_LOOPBACK_TLS_TESTS') == '1', 'explicit loopback TLS opt-in required')
class LoopbackTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cj007-synthetic-tls-',dir='/private/tmp')
        root=Path(cls.temp.name);key=ec.generate_private_key(ec.SECP256R1())
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'CJ007 synthetic loopback only')])
        now=datetime.datetime.now(datetime.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
              .not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
              .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
              .sign(key,hashes.SHA256()))
        (root/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (root/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        cls.server_tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);cls.server_tls.load_cert_chain(root/'cert.pem',root/'key.pem')
        cls.client_tls=ssl.create_default_context(cafile=str(root/'cert.pem'))
        cls.signing=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    @classmethod
    def tearDownClass(cls):
        path=cls.temp.name; cls.temp.cleanup()
        if Path(path).exists(): raise AssertionError('temporary certificate cleanup failed')
        print('temporary_certificate_directory_removed=true')
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.socket=self.server_tls.wrap_socket(self.server.socket,server_side=True)
        self.server.url='https://127.0.0.1:'+str(self.server.server_port)
        self.server.release=threading.Event();self.server.headers_sent=threading.Event()
        self.server.condition=threading.Condition();self.server.active=0;self.server.paths=[]
        key=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.signing.public_key()))|{'kid':'synthetic','alg':'RS256'}
        self.server.document=json.dumps({'keys':[key]}).encode()
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.01),daemon=True);self.thread.start()
    def tearDown(self):
        self.server.release.set();self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.server.socket.fileno(),-1)
        print('listener_closed=127.0.0.1:'+str(self.server.server_port))
        with self.server.condition: self.assertTrue(self.server.condition.wait_for(lambda:self.server.active==0,timeout=2))
    def adapter(self,path,read=.15,trusted=True):
        c=HTTPSConfiguration(self.server.url+path,.15,read,.15,.15,.005,8192,2048)
        return HTTPSJWKSTransport(c,tls_context=self.client_tls if trusted else None)
    def request(self,path,timeout=1): return JWKSRequest(self.server.url+path,timeout,8192,threading.Event())

    def test_real_tls_jwks_and_local_signature(self):
        v=JWTConfiguration('https://issuer.synthetic.invalid','synthetic-aud','RS256',0)
        config=JWKSConfiguration(v.issuer,self.server.url+'/keys','RS256',30,10,1,8192,2048,4,64,4096)
        p=BoundedJWKSProvider(verification=v,configuration=config,transport=self.adapter('/keys'))
        now=int(time.time())
        token=jwt.encode(dict(iss=v.issuer,aud=v.audience,sub='synthetic',iat=now-1,nbf=now-1,exp=now+60),
                         self.signing,algorithm='RS256',headers={'kid':'synthetic'})
        self.assertEqual(PyJWTVerifier(v,p).verify(token).status,VerificationStatus.VALID)
        self.assertEqual(self.server.paths,['/keys'])
    def test_real_redirect_not_followed(self):
        r=self.adapter('/redirect').fetch(self.request('/redirect'))
        self.assertEqual(r.status,302);self.assertEqual(self.server.paths,['/redirect']);self.assertEqual(r.chunks,())
    def test_untrusted_certificate_fails_before_http(self):
        with self.assertRaisesRegex(HTTPTransportFailure,'request_failed'):
            self.adapter('/keys',trusted=False).fetch(self.request('/keys'))
        self.assertEqual(self.server.paths,[])
    def test_live_read_timeout(self):
        started=time.monotonic()
        with self.assertRaisesRegex(HTTPTransportFailure,'read_timeout'):
            self.adapter('/stall').fetch(self.request('/stall'))
        self.assertTrue(self.server.headers_sent.is_set());self.assertLess(time.monotonic()-started,1.5)
        print('live_read_timeout_elapsed_seconds='+format(time.monotonic()-started,'.4f'))
    def test_slow_drip_total_deadline(self):
        started=time.monotonic()
        with self.assertRaisesRegex(HTTPTransportFailure,'total_timeout'):
            self.adapter('/drip',read=.5).fetch(self.request('/drip',.2))
        self.assertLess(time.monotonic()-started,1.5)
        print('slow_drip_total_deadline_elapsed_seconds='+format(time.monotonic()-started,'.4f'))
    def test_live_cancellation_before_read_timeout(self):
        request=self.request('/stall',3);adapter=self.adapter('/stall',read=2);errors=[]
        def run():
            try: adapter.fetch(request)
            except HTTPTransportFailure as error: errors.append(str(error))
        worker=threading.Thread(target=run,daemon=True);worker.start()
        try:
            self.assertTrue(self.server.headers_sent.wait(1));started=time.monotonic()
            request.cancelled.set();worker.join(1)
            self.assertFalse(worker.is_alive());self.assertLess(time.monotonic()-started,1)
            self.assertEqual(errors,['cancelled'])
        finally: request.cancelled.set();self.server.release.set();worker.join(2)
    def test_stalled_tls_handshake_connect_timeout(self):
        sink=socket.socket();sink.bind(('127.0.0.1',0));sink.listen(1);sink.settimeout(1)
        release=threading.Event();accepted=threading.Event()
        def hold():
            try:
                connection,_=sink.accept();accepted.set()
                with connection: release.wait(2)
            except OSError: pass
        thread=threading.Thread(target=hold,daemon=True);thread.start()
        url='https://127.0.0.1:'+str(sink.getsockname()[1])+'/keys'
        adapter=HTTPSJWKSTransport(HTTPSConfiguration(url,.15,.5,.5,.5,.005,8192,32),tls_context=self.client_tls)
        started=time.monotonic()
        try:
            with self.assertRaisesRegex(HTTPTransportFailure,'connect_timeout'):
                adapter.fetch(JWKSRequest(url,1,8192,threading.Event()))
            self.assertTrue(accepted.is_set());self.assertLess(time.monotonic()-started,1.5)
            print('tls_connect_timeout_elapsed_seconds='+format(time.monotonic()-started,'.4f'))
        finally: release.set();sink.close();thread.join(2)
        self.assertFalse(thread.is_alive())


if __name__=='__main__': unittest.main(verbosity=2)
