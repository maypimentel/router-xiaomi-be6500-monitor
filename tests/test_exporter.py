import pytest

from monitor import exporter

from .conftest import FakeRouter, load

MACBIND = "api/xqnetwork/macbind_info"
NOTE = {"mac": "02:00:00:00:00:01", "name": "living-room-laptop", "ip": "192.168.31.101"}
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


def test_collect_wan_connected(fake_router, metric):
    exporter.collect(fake_router)

    assert metric("router_wan_up", wan="WAN1") == 1
    assert metric("router_wan_status_code", wan="WAN1") == 2
    assert metric("router_wan_link_speed_mbps", wan="WAN1") == 1000
    assert metric("router_wan_error_code", wan="WAN1") == 0
    assert metric(
        "router_wan_info", wan="WAN1", proto="dhcp", ip="192.0.2.10",
        gateway="192.0.2.1", dns="192.0.2.53,192.0.2.54", message="",
    ) == 1


def test_collect_wan_disconnected(fake_router, metric):
    exporter.collect(fake_router)

    assert metric("router_wan_up", wan="WAN2") == 0
    assert metric("router_wan_status_code", wan="WAN2") == 3
    assert metric("router_wan_link_speed_mbps", wan="WAN2") == 0  # empty wanSpeed
    assert metric("router_wan_error_code", wan="WAN2") == 678
    assert metric(
        "router_wan_info", wan="WAN2", proto="pppoe", ip="", gateway="", dns="",
        message="无法连接服务器(678)",
    ) == 1


def test_collect_tolerates_missing_fields(router_routes, metric):
    router_routes["api/misystem/get_ps_service?service=multiwan"] = {"code": 0}
    router_routes["api/xqnetwork/get_wan_status"] = {"code": 0}
    router_routes["api/xqnetwork/pppoe_status?wan_name=WAN1"] = {"code": 0}

    exporter.collect(FakeRouter(router_routes))

    assert metric("router_multiwan_enabled") == 0
    assert metric("router_wan_ipv6_up") == 0
    assert metric("router_wan_up", wan="WAN1") == 0
    assert metric("router_wan_info", wan="WAN1", proto="", ip="", gateway="", dns="", message="") == 1


def test_collect_removes_old_wan_info(router_routes, metric):
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


# --- clients (LAN) -----------------------------------------------------------

def test_collect_clients_totals(fake_router, metric):
    exporter.collect_clients(fake_router)

    assert fake_router.calls == [MACBIND]
    assert metric("router_clients_known") == 3
    assert metric("router_clients_online") == 2


def test_collect_clients_statistics(fake_router, metric):
    exporter.collect_clients(fake_router)

    mac = NOTE["mac"]
    assert metric("router_client_download_bytes_per_second", mac=mac) == 350000
    assert metric("router_client_upload_bytes_per_second", mac=mac) == 1200
    assert metric("router_client_download_bytes", mac=mac) == 2147483648
    assert metric("router_client_upload_bytes", mac=mac) == 52428800
    assert metric("router_client_online_seconds", mac=mac) == 28800


def test_collect_clients_metrics_identified_by_mac_only(fake_router):
    exporter.collect_clients(fake_router)

    for gauge in (exporter.cl_up_speed, exporter.cl_down_speed, exporter.cl_up_total,
                  exporter.cl_down_total, exporter.cl_online_s):
        labels = {tuple(s.labels) for m in gauge.collect() for s in m.samples}
        assert labels == {("mac",)}, gauge


def test_collect_clients_info(fake_router, metric):
    exporter.collect_clients(fake_router)

    assert metric("router_client_info", **NOTE, type="wifi", band="wl0") == 1
    assert metric("router_client_info", **ESP, type="wifi", band="wl1") == 1
    assert metric("router_client_info", **TV, type="lan", band="") == 0  # offline


def test_collect_clients_uses_hostname_without_name(fake_router, metric):
    exporter.collect_clients(fake_router)

    # empty "name" in the fixture -> falls back to hostname
    assert metric("router_client_info", **ESP, type="wifi", band="wl1") == 1


def test_collect_clients_rename_keeps_series(router_routes, metric):
    exporter.collect_clients(FakeRouter(router_routes))

    data = load("macbind_info.json")
    note = next(d for d in data["devicelist"] if d["mac"] == NOTE["mac"])
    note["name"] = "office-laptop"
    note["ip"] = note["statistics"]["ip"] = "192.168.31.150"
    router_routes[MACBIND] = data
    exporter.collect_clients(FakeRouter(router_routes))

    # the metric stays in the same series (only the MAC identifies it)...
    assert metric("router_client_download_bytes", mac=NOTE["mac"]) == 2147483648
    # ...and only the info metric changes name/IP
    assert metric("router_client_info", **NOTE, type="wifi", band="wl0") is None
    assert metric(
        "router_client_info", mac=NOTE["mac"], name="office-laptop",
        ip="192.168.31.150", type="wifi", band="wl0",
    ) == 1


def test_collect_clients_removes_clients_that_left(router_routes, metric):
    exporter.collect_clients(FakeRouter(router_routes))
    assert metric("router_client_info", **TV, type="lan", band="") == 0

    data = load("macbind_info.json")
    data["devicelist"] = [d for d in data["devicelist"] if d["mac"] != TV["mac"]]
    router_routes[MACBIND] = data
    exporter.collect_clients(FakeRouter(router_routes))

    assert metric("router_clients_known") == 2
    assert metric("router_client_info", **TV, type="lan", band="") is None
    assert metric("router_client_online_seconds", mac=TV["mac"]) is None
    assert metric("router_client_online_seconds", mac=NOTE["mac"]) == 28800


def test_collect_clients_without_statistics(router_routes, metric):
    data = load("macbind_info.json")
    data["devicelist"] = [{"mac": "02:00:00:00:00:09", "ip": "192.168.31.109", "hostname": "new-device", "online": 1}]
    router_routes[MACBIND] = data

    exporter.collect_clients(FakeRouter(router_routes))

    new = {"mac": "02:00:00:00:00:09", "name": "new-device", "ip": "192.168.31.109"}
    assert metric("router_client_download_bytes_per_second", mac=new["mac"]) == 0
    assert metric("router_client_info", **new, type="", band="") == 1


def test_collect_clients_empty_list(router_routes, metric):
    router_routes[MACBIND] = {"code": 0}

    exporter.collect_clients(FakeRouter(router_routes))

    assert metric("router_clients_known") == 0
    assert metric("router_clients_online") == 0


# --- main loop ---------------------------------------------------------------

class StopLoop(Exception):
    pass


@pytest.fixture
def run_main(monkeypatch):
    """Runs one iteration of exporter.main() with a fake client and server."""

    def _run(collect_side_effect=None):
        monkeypatch.setenv("ROUTER_PASSWORD", "fake-password")
        monkeypatch.setattr(exporter, "start_http_server", lambda port: None)
        instances = []

        class Client:
            def __init__(self, host, password):
                self.token = "some-token"
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


def test_main_marks_collection_ok(run_main, metric):
    run_main()

    assert metric("router_scrape_success") == 1
    assert metric("router_scrape_duration_seconds") >= 0


def test_main_marks_failure_and_drops_token(run_main, metric):
    def boom(c):
        raise RuntimeError("router is down")

    client = run_main(boom)

    assert metric("router_scrape_success") == 0
    assert client.token is None
