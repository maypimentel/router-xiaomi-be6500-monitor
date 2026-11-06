import pytest

from monitor import exporter

from .conftest import FakeRouter, load

MACBIND = "api/xqnetwork/macbind_info"
NOTE = {"mac": "02:00:00:00:00:01", "name": "notebook-sala", "ip": "192.168.31.101"}
ESP = {"mac": "02:00:00:00:00:02", "name": "sensor-esp", "ip": "192.168.31.102"}
TV = {"mac": "02:00:00:00:00:03", "name": "tv", "ip": "192.168.31.103"}


# --- WAN ---------------------------------------------------------------------

def test_collect_multiwan(fake_router, metric):
    exporter.collect(fake_router)

    assert metric("router_multiwan_enabled") == 1
    assert metric("router_multiwan_policy_mode") == 1
    assert metric("router_multiwan_current_wan", wan="WAN1") == 0
    assert metric("router_multiwan_current_wan", wan="WAN2") == 1
    assert metric("router_multiwan_weight", wan="WAN1") == 3
    assert metric("router_multiwan_weight", wan="WAN2") == 1
    assert metric("router_multiwan_bandwidth", wan="WAN1") == 500
    assert metric("router_multiwan_bandwidth", wan="WAN2") == 300
    assert metric("router_wan_ipv6_up") == 1


def test_collect_wan_conectada(fake_router, metric):
    exporter.collect(fake_router)

    assert metric("router_wan_up", wan="WAN1") == 1
    assert metric("router_wan_status_code", wan="WAN1") == 2
    assert metric("router_wan_link_speed_mbps", wan="WAN1") == 1000
    assert metric("router_wan_error_code", wan="WAN1") == 0
    assert metric(
        "router_wan_info", wan="WAN1", proto="dhcp", ip="192.0.2.10",
        gateway="192.0.2.1", dns="192.0.2.53,192.0.2.54", message="",
    ) == 1


def test_collect_wan_desconectada(fake_router, metric):
    exporter.collect(fake_router)

    assert metric("router_wan_up", wan="WAN2") == 0
    assert metric("router_wan_status_code", wan="WAN2") == 3
    assert metric("router_wan_link_speed_mbps", wan="WAN2") == 0  # wanSpeed vazio
    assert metric("router_wan_error_code", wan="WAN2") == 678
    assert metric(
        "router_wan_info", wan="WAN2", proto="pppoe", ip="", gateway="", dns="",
        message="无法连接服务器(678)",
    ) == 1


def test_collect_tolera_campos_ausentes(router_routes, metric):
    router_routes["api/misystem/get_ps_service?service=multiwan"] = {"code": 0}
    router_routes["api/xqnetwork/get_wan_status"] = {"code": 0}
    router_routes["api/xqnetwork/pppoe_status?wan_name=WAN1"] = {"code": 0}

    exporter.collect(FakeRouter(router_routes))

    assert metric("router_multiwan_enabled") == 0
    assert metric("router_wan_ipv6_up") == 0
    assert metric("router_wan_up", wan="WAN1") == 0
    assert metric("router_wan_info", wan="WAN1", proto="", ip="", gateway="", dns="", message="") == 1


def test_collect_remove_wan_info_antigo(router_routes, metric):
    exporter.collect(FakeRouter(router_routes))
    old_ip = {"wan": "WAN1", "proto": "dhcp", "ip": "192.0.2.10", "gateway": "192.0.2.1",
              "dns": "192.0.2.53,192.0.2.54", "message": ""}
    assert metric("router_wan_info", **old_ip) == 1

    wan1 = load("pppoe_wan1_up.json")
    wan1["ip"]["address"] = "192.0.2.20"
    router_routes["api/xqnetwork/pppoe_status?wan_name=WAN1"] = wan1
    exporter.collect(FakeRouter(router_routes))

    assert metric("router_wan_info", **old_ip) is None
    assert metric("router_wan_info", **{**old_ip, "ip": "192.0.2.20"}) == 1


# --- clientes (LAN) ----------------------------------------------------------

def test_collect_clients_totais(fake_router, metric):
    exporter.collect_clients(fake_router)

    assert fake_router.calls == [MACBIND]
    assert metric("router_clients_known") == 3
    assert metric("router_clients_online") == 2


def test_collect_clients_estatisticas(fake_router, metric):
    exporter.collect_clients(fake_router)

    assert metric("router_client_download_bytes_per_second", **NOTE) == 350000
    assert metric("router_client_upload_bytes_per_second", **NOTE) == 1200
    assert metric("router_client_download_bytes", **NOTE) == 2147483648
    assert metric("router_client_upload_bytes", **NOTE) == 52428800
    assert metric("router_client_online_seconds", **NOTE) == 28800


def test_collect_clients_info(fake_router, metric):
    exporter.collect_clients(fake_router)

    assert metric("router_client_info", **NOTE, type="wifi", band="wl0") == 1
    assert metric("router_client_info", **ESP, type="wifi", band="wl1") == 1
    assert metric("router_client_info", **TV, type="lan", band="") == 0  # offline


def test_collect_clients_usa_hostname_sem_nome(fake_router, metric):
    exporter.collect_clients(fake_router)

    # "name" vazio na fixture -> cai para o hostname
    assert metric("router_client_download_bytes_per_second", **ESP) == 8


def test_collect_clients_remove_quem_saiu_da_lista(router_routes, metric):
    exporter.collect_clients(FakeRouter(router_routes))
    assert metric("router_client_info", **TV, type="lan", band="") == 0

    data = load("macbind_info.json")
    data["devicelist"] = [d for d in data["devicelist"] if d["mac"] != TV["mac"]]
    router_routes[MACBIND] = data
    exporter.collect_clients(FakeRouter(router_routes))

    assert metric("router_clients_known") == 2
    assert metric("router_client_info", **TV, type="lan", band="") is None
    assert metric("router_client_online_seconds", **TV) is None
    assert metric("router_client_online_seconds", **NOTE) == 28800


def test_collect_clients_sem_statistics(router_routes, metric):
    data = load("macbind_info.json")
    data["devicelist"] = [{"mac": "02:00:00:00:00:09", "ip": "192.168.31.109", "hostname": "novo", "online": 1}]
    router_routes[MACBIND] = data

    exporter.collect_clients(FakeRouter(router_routes))

    novo = {"mac": "02:00:00:00:00:09", "name": "novo", "ip": "192.168.31.109"}
    assert metric("router_client_download_bytes_per_second", **novo) == 0
    assert metric("router_client_info", **novo, type="", band="") == 1


def test_collect_clients_lista_vazia(router_routes, metric):
    router_routes[MACBIND] = {"code": 0}

    exporter.collect_clients(FakeRouter(router_routes))

    assert metric("router_clients_known") == 0
    assert metric("router_clients_online") == 0


# --- main loop ---------------------------------------------------------------

class StopLoop(Exception):
    pass


@pytest.fixture
def run_main(monkeypatch):
    """Executa uma iteração de exporter.main() com cliente e servidor falsos."""

    def _run(collect_side_effect=None):
        monkeypatch.setenv("ROUTER_PASSWORD", "senha-ficticia")
        monkeypatch.setattr(exporter, "start_http_server", lambda port: None)
        instances = []

        class Client:
            def __init__(self, host, password):
                self.token = "algum-token"
                instances.append(self)

        monkeypatch.setattr(exporter, "MiWifiClient", Client)
        monkeypatch.setattr(exporter, "collect", collect_side_effect or (lambda c: None))
        monkeypatch.setattr(exporter, "collect_clients", lambda c: None)

        def stop(_):
            raise StopLoop

        monkeypatch.setattr(exporter.time, "sleep", stop)
        with pytest.raises(StopLoop):
            exporter.main()
        return instances[0]

    return _run


def test_main_marca_coleta_ok(run_main, metric):
    run_main()

    assert metric("router_scrape_success") == 1
    assert metric("router_scrape_duration_seconds") >= 0


def test_main_marca_falha_e_descarta_token(run_main, metric):
    def boom(c):
        raise RuntimeError("roteador fora do ar")

    client = run_main(boom)

    assert metric("router_scrape_success") == 0
    assert client.token is None
