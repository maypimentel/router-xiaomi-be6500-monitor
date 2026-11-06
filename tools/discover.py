"""Logs in to the router, downloads the home page and lists the API/JSON URLs it references."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from monitor.miwifi import MiWifiClient

c = MiWifiClient(os.environ.get("ROUTER_HOST", "192.168.31.1"), os.environ["ROUTER_PASSWORD"])
c.login()
print("login ok")
html = c.get("web/home").text
open("home.html", "w").write(html)
for m in sorted(set(re.findall(r"['\"]((?:/cgi-bin/luci/)?(?:;stok=[^/]*/)?api/[A-Za-z0-9_/]+)", html))):
    print(m)
for m in sorted(set(re.findall(r"['\"]([^'\"]+\.js[^'\"]*)['\"]", html))):
    print("js:", m)
