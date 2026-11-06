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
    c = MiWifiClient("192.0.2.1", "senha-ficticia")
    c.session = fake_session
    return c


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# --- login -------------------------------------------------------------------

def test_login_envia_hash_da_senha_e_guarda_token(client, fake_session):
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))

    assert client.login() == TOKEN
    assert client.token == TOKEN

    url, data = fake_session.posts[0]
    assert url == "http://192.0.2.1/cgi-bin/luci/api/xqsystem/login"
    assert data["username"] == "admin"
    assert data["logtype"] == 2
    nonce = data["nonce"]
    assert nonce.startswith(f"0_{miwifi.DEVICE_ID}_")
    assert data["password"] == sha(nonce + sha("senha-ficticia" + miwifi.KEY))
    assert "senha-ficticia" not in str(data)


def test_login_recusado_levanta_erro(client, fake_session):
    fake_session.post_responses.append(FakeResponse(load("login_fail.json")))

    with pytest.raises(RuntimeError, match="Login falhou"):
        client.login()
    assert client.token is None


def test_login_com_erro_http_levanta_erro(client, fake_session):
    fake_session.post_responses.append(FakeResponse({}, status_code=500))

    with pytest.raises(requests.HTTPError):
        client.login()


# --- get ---------------------------------------------------------------------

def test_get_faz_login_quando_nao_ha_token(client, fake_session):
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))
    fake_session.get_responses.append(FakeResponse(load("macbind_info.json")))

    r = client.get("/" + PATH)

    assert r.json()["code"] == 0
    assert len(fake_session.posts) == 1
    assert fake_session.gets == [f"http://192.0.2.1/cgi-bin/luci/;stok={TOKEN}/{PATH}"]


def test_get_reaproveita_token_existente(client, fake_session):
    client.token = TOKEN
    fake_session.get_responses += [FakeResponse(load("macbind_info.json"))] * 2

    client.get(PATH)
    client.get(PATH)

    assert fake_session.posts == []
    assert len(fake_session.gets) == 2


def test_get_reloga_quando_token_expira_com_http_200(client, fake_session):
    """O roteador responde sessão expirada com HTTP 200 e {"code": 401}."""
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
def test_get_reloga_em_http_401_403(client, fake_session, status):
    client.token = "0" * 32
    fake_session.get_responses += [
        FakeResponse(None, status_code=status, text="denied"),
        FakeResponse(load("macbind_info.json")),
    ]
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))

    assert client.get(PATH).json()["code"] == 0
    assert len(fake_session.posts) == 1


def test_get_falha_se_sessao_continua_recusada(client, fake_session):
    client.token = "0" * 32
    fake_session.get_responses += [FakeResponse(load("invalid_token.json"))] * 2
    fake_session.post_responses.append(FakeResponse(load("login_ok.json")))

    with pytest.raises(RuntimeError, match="Sessão recusada"):
        client.get(PATH)
    assert client.token is None  # força novo login na próxima coleta


def test_get_nao_reloga_em_codigo_de_erro_da_wan(client, fake_session):
    """WAN fora do ar responde code 1604: é dado válido, não sessão expirada."""
    client.token = TOKEN
    fake_session.get_responses.append(FakeResponse(load("pppoe_wan2_down.json")))

    r = client.get("api/xqnetwork/pppoe_status?wan_name=WAN2")

    assert r.json()["code"] == 1604
    assert fake_session.posts == []
    assert client.token == TOKEN


def test_get_aceita_resposta_que_nao_e_json(client, fake_session):
    client.token = TOKEN
    fake_session.get_responses.append(FakeResponse(None, text="<html>home</html>"))

    assert client.get("web/home").text == "<html>home</html>"
    assert fake_session.posts == []


def test_get_propaga_erro_http(client, fake_session):
    client.token = TOKEN
    fake_session.get_responses.append(FakeResponse(None, status_code=500, text="erro"))

    with pytest.raises(requests.HTTPError):
        client.get(PATH)
