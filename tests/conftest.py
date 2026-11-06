"""Fixtures compartilhadas. Todos os dados em tests/fixtures são fictícios."""
import json
from pathlib import Path

import pytest
import requests
from prometheus_client import REGISTRY

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    """Resposta mínima compatível com o uso de requests.Response no projeto."""

    def __init__(self, payload=None, status_code: int = 200, text: str | None = None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise requests.exceptions.JSONDecodeError("not json", self.text, 0)
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Substitui requests.Session: devolve respostas enfileiradas e registra as chamadas."""

    def __init__(self):
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []
        self.post_responses: list[FakeResponse] = []
        self.get_responses: list[FakeResponse] = []

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data))
        return self.post_responses.pop(0)

    def get(self, url, timeout=None):
        self.gets.append(url)
        return self.get_responses.pop(0)


class FakeRouter:
    """Cliente falso para o exporter: mapeia path da API -> fixture."""

    def __init__(self, routes: dict[str, dict]):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, path: str):
        self.calls.append(path)
        return FakeResponse(self.routes[path])


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def router_routes():
    return {
        "api/misystem/get_ps_service?service=multiwan": load("multiwan.json"),
        "api/xqnetwork/get_wan_status": load("wan_status.json"),
        "api/xqnetwork/pppoe_status?wan_name=WAN1": load("pppoe_wan1_up.json"),
        "api/xqnetwork/pppoe_status?wan_name=WAN2": load("pppoe_wan2_down.json"),
        "api/xqnetwork/macbind_info": load("macbind_info.json"),
    }


@pytest.fixture
def fake_router(router_routes):
    return FakeRouter(router_routes)


@pytest.fixture
def metric():
    """Lê o valor atual de uma métrica do registry global do prometheus_client."""

    # Posicional-only: os clientes têm um label chamado "name".
    def _get(metric_name: str, /, **labels):
        return REGISTRY.get_sample_value(metric_name, labels or None)

    return _get
