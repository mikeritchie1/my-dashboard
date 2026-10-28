from functools import partial
from http.server import ThreadingHTTPServer
import json
import threading
import time
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import serve_dashboard as local
from services.common.dashboard_auth import issue_session, valid_session, password_matches, LoginLimiter, SESSION_SECONDS


class SessionTests(TestCase):
    def test_password_and_session(self):
        self.assertTrue(password_matches("test-password", "test-password"))
        self.assertFalse(password_matches("wrong", "test-password"))
        self.assertFalse(password_matches("", ""))
        token = issue_session("test-password")
        self.assertTrue(valid_session(token, "test-password"))
        self.assertFalse(valid_session(token, "new-password"))
        self.assertFalse(valid_session(token + "tampered", "test-password"))
        for value in ("", "x.y", "x.y.z", None):
            self.assertFalse(valid_session(value, "test-password"))

    def test_expiration(self):
        token = issue_session("test-password")
        with patch("services.common.dashboard_auth.time.time", return_value=time.time() + 86400):
            self.assertTrue(valid_session(token, "test-password"))
        with patch("services.common.dashboard_auth.time.time", return_value=time.time() + SESSION_SECONDS + 1):
            self.assertFalse(valid_session(token, "test-password"))

    def test_throttle(self):
        limiter = LoginLimiter()
        for _ in range(5):
            self.assertTrue(limiter.allow("client"))
        self.assertFalse(limiter.allow("client"))
        self.assertTrue(limiter.allow("other-client"))


class LoginHttpTests(TestCase):
    def setUp(self):
        password_patch = patch.object(local, "secret", return_value="test-password")
        password_patch.start()
        self.addCleanup(password_patch.stop)
        limiter_patch = patch.object(local, "LOGIN_LIMITER", LoginLimiter())
        limiter_patch.start()
        self.addCleanup(limiter_patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(local.DashboardHandler, jobs=None))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def login(self, password, **headers):
        return urlopen(Request(self.base + "/api/auth/login", data=json.dumps({"password": password}).encode(),
                               headers={"Content-Type": "application/json", **headers}))

    def test_login_and_session(self):
        with self.login("test-password") as response:
            self.assertEqual("no-store", response.headers["Cache-Control"])
            token = json.load(response)["token"]
        with urlopen(Request(self.base + "/api/auth/session", headers={"Authorization": "Bearer " + token})) as response:
            self.assertTrue(json.load(response)["authenticated"])

    def test_invalid_login_and_session(self):
        with self.assertRaises(HTTPError) as error:
            self.login("wrong")
        self.assertEqual(401, error.exception.code)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/api/auth/session")
        self.assertEqual(401, error.exception.code)

    def test_unconfigured_and_cross_origin(self):
        with patch.object(local, "secret", return_value=""):
            with self.assertRaises(HTTPError) as error:
                self.login("anything")
            self.assertEqual(503, error.exception.code)
        with self.assertRaises(HTTPError) as error:
            self.login("test-password", Origin="https://other.example")
        self.assertEqual(403, error.exception.code)
