import hashlib

import pytest
import requests

from monitor import miwifi
from monitor.miwifi import MiWifiClient

from .conftest import FakeResponse, load

TOKEN = "feedfacefeedfacefeedfacefeedface"
PATH = "api/xqnetwork/macbind_info"


@pytest.fixture
def client(fake_session):
    c = MiWifiClient("192.0.2.1", "fake-password")
    c.session = fake_session
    return c


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# --- login -------------------------------------------------------------------

def test_login_sends_password_hash_and_stores_token(client, fake_session):
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))

    assert client.login() == TOKEN
    assert client.token == TOKEN

    url, data = fake_session.posts[0]
    assert url == "http://192.0.2.1/cgi-bin/luci/api/xqsystem/login"
    assert data["username"] == "admin"
    assert data["logtype"] == 2
    nonce = data["nonce"]
    assert nonce.startswith(f"0_{miwifi.DEVICE_ID}_")
    assert data["password"] == sha(nonce + sha("fake-password" + miwifi.KEY))
    assert "fake-password" not in str(data)


def test_login_rejected_raises(client, fake_session):
    fake_session.post_responses.append(FakeResponse(load("login_fail.json")))

    with pytest.raises(RuntimeError, match="Login failed"):
        client.login()
    assert client.token is None


def test_login_http_error_raises(client, fake_session):
    fake_session.post_responses.append(FakeResponse({}, status_code=500))

    with pytest.raises(requests.HTTPError):
        client.login()


# --- get ---------------------------------------------------------------------

def test_get_logs_in_when_there_is_no_token(client, fake_session):
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))
    fake_session.get_responses.append(FakeResponse(load("macbind_info.json")))

    r = client.get("/" + PATH)

    assert r.json()["code"] == 0
    assert len(fake_session.posts) == 1
    assert fake_session.gets == [f"http://192.0.2.1/cgi-bin/luci/;stok={TOKEN}/{PATH}"]


def test_get_reuses_existing_token(client, fake_session):
    client.token = TOKEN
    fake_session.get_responses += [FakeResponse(load("macbind_info.json"))] * 2

    client.get(PATH)
    client.get(PATH)

    assert fake_session.posts == []
    assert len(fake_session.gets) == 2


def test_get_relogins_when_token_expires_with_http_200(client, fake_session):
    """The router answers an expired session with HTTP 200 and {"code": 401}."""
    client.token = "0" * 32
    fake_session.get_responses += [
        FakeResponse(load("invalid_token.json")),
        FakeResponse(load("macbind_info.json")),
    ]
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))

    r = client.get(PATH)

    assert r.json()["code"] == 0
    assert len(fake_session.posts) == 1
    assert client.token == TOKEN
    assert fake_session.gets[1].endswith(f";stok={TOKEN}/{PATH}")


@pytest.mark.parametrize("status", [401, 403])
def test_get_relogins_on_http_401_403(client, fake_session, status):
    client.token = "0" * 32
    fake_session.get_responses += [
        FakeResponse(None, status_code=status, text="denied"),
        FakeResponse(load("macbind_info.json")),
    ]
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))

    assert client.get(PATH).json()["code"] == 0
    assert len(fake_session.posts) == 1


def test_get_fails_if_session_keeps_being_rejected(client, fake_session):
    client.token = "0" * 32
    fake_session.get_responses += [FakeResponse(load("invalid_token.json"))] * 2
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))

    with pytest.raises(RuntimeError, match="Session rejected"):
        client.get(PATH)
    assert client.token is None  # forces a new login on the next scrape


def test_get_does_not_relogin_on_wan_error_code(client, fake_session):
    """A down WAN answers code 1604: valid data, not an expired session."""
    client.token = TOKEN
    fake_session.get_responses.append(FakeResponse(load("pppoe_wan2_down.json")))

    r = client.get("api/xqnetwork/pppoe_status?wan_name=WAN2")

    assert r.json()["code"] == 1604
    assert fake_session.posts == []
    assert client.token == TOKEN


def test_get_accepts_non_json_response(client, fake_session):
    client.token = TOKEN
    fake_session.get_responses.append(FakeResponse(None, text="<html>home</html>"))

    assert client.get("web/home").text == "<html>home</html>"
    assert fake_session.posts == []


def test_get_propagates_http_error(client, fake_session):
    client.token = TOKEN
    fake_session.get_responses.append(FakeResponse(None, status_code=500, text="error"))

    with pytest.raises(requests.HTTPError):
        client.get(PATH)
