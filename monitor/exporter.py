"""Exporter Prometheus para os links WAN do Xiaomi BE6500."""
import logging
import os
import time

from prometheus_client import Gauge, start_http_server

from .miwifi import MiWifiClient

log = logging.getLogger("exporter")

# Significado de `status` em pppoe_status (do JS do roteador).
# 1=discando, 2=conectado, 3=falha (tentando modo especial), 4=desconectado.
L = ["wan"]
up = Gauge("router_scrape_success", "1 se a última coleta no roteador funcionou")
scrape_duration = Gauge("router_scrape_duration_seconds", "Duração da última coleta")
mw_enabled = Gauge("router_multiwan_enabled", "1 se multiwan está habilitado")
mw_mode = Gauge("router_multiwan_policy_mode", "Modo da política (0=balanceamento, 1/2=failover, 3=só WAN1, 4=só WAN2)")
mw_current = Gauge("router_multiwan_current_wan", "1 para a WAN atualmente ativa", L)
mw_weight = Gauge("router_multiwan_weight", "Peso no balanceamento", L)
mw_bw = Gauge("router_multiwan_bandwidth", "Banda configurada para a WAN", L)
wan_up = Gauge("router_wan_up", "1 se a WAN está conectada (status==2)", L)
wan_status = Gauge("router_wan_status_code", "Código de status bruto (1=discando,2=ok,3=falha,4=desconectado)", L)
wan_speed = Gauge("router_wan_link_speed_mbps", "Velocidade negociada da porta", L)
wan_err = Gauge("router_wan_error_code", "Código de erro (ex.: 678 PPPoE sem resposta)", L)
wan_info = Gauge("router_wan_info", "Informações da WAN como labels (valor sempre 1)", ["wan", "proto", "ip", "gateway", "dns", "message"])
ipv6_up = Gauge("router_wan_ipv6_up", "1 se o IPv6 da WAN principal está ativo")

# As métricas por cliente são identificadas só pelo MAC, para o histórico não
# se partir quando o aparelho é renomeado ou troca de IP. Nome, IP, tipo e
# rádio ficam em router_client_info; os dashboards fazem o join por `mac`.
CL = ["mac"]
clients_online = Gauge("router_clients_online", "Número de clientes online")
clients_total = Gauge("router_clients_known", "Número de clientes na lista do roteador")
cl_up_speed = Gauge("router_client_upload_bytes_per_second", "Velocidade de upload atual do cliente", CL)
cl_down_speed = Gauge("router_client_download_bytes_per_second", "Velocidade de download atual do cliente", CL)
cl_up_total = Gauge("router_client_upload_bytes", "Total enviado pelo cliente na sessão (bytes)", CL)
cl_down_total = Gauge("router_client_download_bytes", "Total recebido pelo cliente na sessão (bytes)", CL)
cl_online_s = Gauge("router_client_online_seconds", "Tempo conectado (s)", CL)
cl_info = Gauge(
    "router_client_info", "Nome, IP, tipo e rádio do cliente como labels (valor 1 se online)",
    ["mac", "name", "ip", "type", "band"],
)

WANS = {"wan": "WAN1", "wan_2": "WAN2"}


def collect(c: MiWifiClient) -> None:
    mw = c.get("api/misystem/get_ps_service?service=multiwan").json().get("multiwan", {})
    pol = mw.get("policy", {})
    mw_enabled.set(int(mw.get("enable", 0)))
    mw_mode.set(int(pol.get("mode", 0)))
    for key, name in WANS.items():
        mw_current.labels(name).set(1 if pol.get("currwan") == key else 0)
    mw_weight.labels("WAN1").set(float(pol.get("weight1") or 0))
    mw_weight.labels("WAN2").set(float(pol.get("weight2") or 0))
    mw_bw.labels("WAN1").set(float(pol.get("bandwidth_wan1") or 0))
    mw_bw.labels("WAN2").set(float(pol.get("bandwidth_wan2") or 0))

    v6 = c.get("api/xqnetwork/get_wan_status").json().get("ipv6", {}).get("wan6_info", {})
    ipv6_up.set(1 if v6.get("up") else 0)

    wan_info.clear()
    for name in WANS.values():
        d = c.get(f"api/xqnetwork/pppoe_status?wan_name={name}").json()
        status = int(d.get("status", 0) or 0)
        wan_up.labels(name).set(1 if status == 2 else 0)
        wan_status.labels(name).set(status)
        wan_speed.labels(name).set(float(d.get("wanSpeed") or 0))
        wan_err.labels(name).set(int(d.get("errcode", 0) or 0))
        wan_info.labels(
            name, d.get("proto", ""), (d.get("ip") or {}).get("address", ""),
            d.get("gw", ""), ",".join(d.get("dns") or []), d.get("msg", ""),
        ).set(1)


def collect_clients(c: MiWifiClient) -> None:
    devs = c.get("api/xqnetwork/macbind_info").json().get("devicelist", [])
    for g in (cl_up_speed, cl_down_speed, cl_up_total, cl_down_total, cl_online_s, cl_info):
        g.clear()  # evita séries de clientes que saíram da lista
    clients_total.set(len(devs))
    clients_online.set(sum(1 for d in devs if d.get("online")))
    for d in devs:
        st = d.get("statistics") or {}
        mac = d.get("mac", "")
        num = lambda k: float(st.get(k) or 0)  # noqa: E731
        cl_up_speed.labels(mac).set(num("upspeed"))
        cl_down_speed.labels(mac).set(num("downspeed"))
        cl_up_total.labels(mac).set(num("upload"))
        cl_down_total.labels(mac).set(num("download"))
        cl_online_s.labels(mac).set(num("online"))
        cl_info.labels(
            mac, d.get("name") or d.get("hostname") or "", d.get("ip", ""),
            d.get("type", ""), st.get("dev", ""),
        ).set(1 if d.get("online") else 0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("ROUTER_HOST", "192.168.31.1")
    password = os.environ["ROUTER_PASSWORD"]
    interval = float(os.environ.get("SCRAPE_INTERVAL", "15"))
    port = int(os.environ.get("EXPORTER_PORT", "9877"))
    client = MiWifiClient(host, password)
    start_http_server(port)
    log.info("exporter na porta %s, roteador %s, intervalo %ss", port, host, interval)
    while True:
        t0 = time.time()
        try:
            collect(client)
            collect_clients(client)
            up.set(1)
        except Exception as e:  # noqa: BLE001
            log.error("coleta falhou: %s", e)
            client.token = None
            up.set(0)
        scrape_duration.set(time.time() - t0)
        time.sleep(max(1.0, interval - (time.time() - t0)))


if __name__ == "__main__":
    main()
