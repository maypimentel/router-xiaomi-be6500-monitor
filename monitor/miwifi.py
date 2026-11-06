"""Minimal client for the web interface of Xiaomi (MiWiFi) routers."""
import hashlib
import random
import re
import time

import requests

# Constants taken from the login page JS (/cgi-bin/luci/web).
KEY = "a2ffa5c9be07488bbb04a3a47d3c5f6a"
DEVICE_ID = "00:d7:6d:1b:1c:e1"


class MiWifiClient:
    def __init__(self, host: str, password: str, timeout: float = 10):
        self.base = f"http://{host}"
        self.password = password
        self.timeout = timeout
        self.token: str | None = None
        self.session = requests.Session()

    @staticmethod
    def _sha256(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    def login(self) -> str:
        nonce = f"0_{DEVICE_ID}_{int(time.time())}_{random.randint(0, 9999)}"
        pwd = self._sha256(nonce + self._sha256(self.password + KEY))
        r = self.session.post(
            f"{self.base}/cgi-bin/luci/api/xqsystem/login",
            data={"username": "admin", "password": pwd, "logtype": 2, "nonce": nonce},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Login failed: {data}")
        self.token = data["token"]
        return self.token

    def get(self, path: str):
        """Authenticated GET on /cgi-bin/luci/;stok=<token>/<path>. Logs in again if the session expired."""
        for attempt in (1, 2):
            if not self.token:
                self.login()
            r = self.session.get(
                f"{self.base}/cgi-bin/luci/;stok={self.token}/{path.lstrip('/')}",
                timeout=self.timeout,
            )
            if r.status_code in (401, 403) or self._invalid_token(r):
                self.token = None
                if attempt == 1:
                    continue
                raise RuntimeError(f"Session rejected by the router on {path}")
            r.raise_for_status()
            return r

    @staticmethod
    def _invalid_token(r: requests.Response) -> bool:
        # An expired token comes back as HTTP 200 with {"code":401,"msg":"Invalid token"}.
        try:
            return r.json().get("code") == 401
        except ValueError:
            return False
