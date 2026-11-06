# Monitor WAN/LAN – Xiaomi BE6500

**Português** | [English](README.en.md)

[![Testes](https://github.com/maypimentel/router-xiaomi-be6500-monitor/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/maypimentel/router-xiaomi-be6500-monitor/actions/workflows/tests.yml?query=branch%3Amain)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)
[![Python 3.14](https://img.shields.io/badge/python-3.14-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3140/)

<p align="center">
  <img src="https://cdn.cnbj1.fds.api.mi-img.com/product-images/xiaomi-routers/be-6500b8474/062.jpg" alt="Roteador Xiaomi BE6500" width="600">
  <br><sub>Imagem: <a href="https://www.mi.com/xiaomi-routers/be-6500/">Xiaomi</a> (página oficial do produto)</sub>
</p>

Monitoramento do roteador Xiaomi BE6500 com Prometheus e Grafana. Um exporter em Python faz login na interface web do roteador, coleta o estado das WANs (multiwan, PPPoE/DHCP, IPv6) e dos clientes da LAN, e expõe tudo em formato Prometheus. A stack (exporter + Prometheus + Grafana) sobe com Docker Compose e já vem com dashboards e alertas.

## Início rápido
Pré-requisitos: Docker com Compose e acesso ao roteador pela rede local.

```shell
cp .env.example .env   # preencha ROUTER_PASSWORD
docker compose up -d --build
```

Abra o Grafana em http://localhost:3000 (usuário e senha padrão `admin`/`admin`; troque em `GRAFANA_PASSWORD` antes de subir). Os dashboards ficam em **Dashboards**.

> O Grafana fica exposto em todas as interfaces da máquina na porta `GRAFANA_PORT`. Prometheus e exporter não são expostos; só o Grafana os acessa, pela rede interna do Compose.

## Configuração (`.env`)
| Variável | Padrão | Descrição |
|---|---|---|
| `ROUTER_PASSWORD` | (obrigatória) | Senha de administrador da interface web do roteador. Só é igual à do Wi-Fi se você escolheu isso na configuração inicial. |
| `ROUTER_HOST` | `192.168.31.1` | Endereço do roteador. |
| `SCRAPE_INTERVAL` | `15` | Intervalo de coleta do exporter, em segundos. |
| `RETENTION` | `90d` | Por quanto tempo o Prometheus guarda os dados. |
| `GRAFANA_USER` / `GRAFANA_PASSWORD` | `admin` / `admin` | Login do Grafana. |
| `GRAFANA_PORT` | `3000` | Porta do Grafana na máquina. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | (vazio) | Alertas no Telegram; veja [Alertas](#alertas). |

Depois de mudar o `.env`, rode `docker compose up -d` para aplicar.

## Dashboards
**Xiaomi BE6500 - WANs**: estado de cada WAN, WAN ativa no multiwan, política, velocidade do link, códigos de status e erro, e detalhes (IP, gateway, DNS).

![Dashboard WAN](./docs/images/WAN-dashboard.png)

**Xiaomi BE6500 - LAN (clients)**: clientes online, velocidade de download/upload por cliente (top 10), ranking dos 10 maiores volumes de download e de upload, e tabela com todos os clientes.

![Dashboard LAN](./docs/images/LAN-dashboard.png)

Os dashboards são provisionados a partir de `grafana/dashboards/*.json`: alterações feitas pela interface do Grafana não podem ser salvas. Para mudar um painel, edite o JSON (ou exporte o dashboard pelo Grafana e substitua o arquivo); o Grafana recarrega sozinho.

## Alertas
Regras provisionadas em `grafana/provisioning/alerting/`:

| Arquivo | Alerta | Dispara quando |
|---|---|---|
| `wan-alerts.yml` | WAN1 down | WAN1 desconectada por 1 min |
| `wan-alerts.yml` | WAN2 down (multiwan enabled) | WAN2 desconectada por 1 min, com o multiwan habilitado |
| `wan-alerts.yml` | Router not responding | O exporter não consegue coletar por 2 min |
| `lan-alerts.yml` | New device on the network | Aparece um MAC não visto nos 7 dias anteriores. Só começa a avaliar após ~30 min de coleta. |

### Telegram (desativado por padrão)
Sem o Telegram, os alertas aparecem só na interface do Grafana (**Alerting**). Para receber no Telegram:

1. Crie um bot com o `@BotFather` e copie o token.
2. Mande uma mensagem ao bot (ou adicione-o ao grupo) e obtenha o chat id em `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. Preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`.
4. Ative o contact point e suba de novo:
   ```shell
   rm grafana/provisioning/alerting/telegram-off.yml
   mv grafana/provisioning/alerting/telegram.yml.disabled grafana/provisioning/alerting/telegram.yml
   docker compose up -d
   ```

## Métricas
Expostas pelo exporter na porta `9877` (rede interna do Compose).

| Métrica | Labels | Descrição |
|---|---|---|
| `router_scrape_success` | | 1 se a última coleta funcionou |
| `router_scrape_duration_seconds` | | Duração da última coleta |
| `router_multiwan_enabled` | | 1 se o multiwan está habilitado |
| `router_multiwan_policy_mode` | | 0=balanceamento, 1/2=failover, 3=só WAN1, 4=só WAN2 |
| `router_multiwan_current_wan` | `wan` | 1 para a WAN ativa |
| `router_multiwan_weight`, `router_multiwan_bandwidth` | `wan` | Peso e banda configurados |
| `router_wan_up` | `wan` | 1 se a WAN está conectada |
| `router_wan_status_code` | `wan` | 1=discando, 2=ok, 3=falha, 4=desconectado |
| `router_wan_link_speed_mbps` | `wan` | Velocidade negociada da porta |
| `router_wan_error_code` | `wan` | Código de erro (ex.: 678 = PPPoE sem resposta) |
| `router_wan_info` | `wan`, `proto`, `ip`, `gateway`, `dns`, `message` | Detalhes da WAN (valor sempre 1) |
| `router_wan_ipv6_up` | | 1 se o IPv6 da WAN principal está ativo |
| `router_clients_online`, `router_clients_known` | | Clientes online e total na lista do roteador |
| `router_client_download_bytes_per_second`, `router_client_upload_bytes_per_second` | `mac` | Velocidade atual do cliente |
| `router_client_download_bytes`, `router_client_upload_bytes` | `mac` | Volume desde que o cliente conectou (zera ao reconectar) |
| `router_client_online_seconds` | `mac` | Tempo conectado |
| `router_client_info` | `mac`, `name`, `ip`, `type`, `band` | Nome, IP, tipo e rádio do cliente (1 se online) |

As métricas por cliente são identificadas só pelo MAC, para o histórico não se partir quando o aparelho é renomeado ou troca de IP. Para obter o nome, faça o join com `router_client_info`:
```promql
router_client_download_bytes * on(mac) group_left(name, ip) router_client_info
```

### Endpoints do roteador usados
- `api/misystem/get_ps_service?service=multiwan` – habilitado, política, WAN ativa, pesos
- `api/xqnetwork/get_wan_status` – IPv4/IPv6 da WAN principal
- `api/xqnetwork/pppoe_status?wan_name=WAN1|WAN2` – status/erro/velocidade de cada WAN
- `api/xqnetwork/macbind_info` – clientes: online, IP, rádio, velocidade e consumo

## Atualizar
```shell
git pull
docker compose up -d --build
```
Os dados do Prometheus e do Grafana ficam em volumes do Docker e são mantidos.

## Descobrir endpoints da API (`tools/discover.py`)
O script faz login no roteador, baixa a página inicial da interface web e lista as URLs de API (`api/...`) e os arquivos `.js` que ela referencia. A página completa fica salva em `home.html` (ignorado pelo git) para inspeção manual.

**Quando rodar**
- Depois de atualizar o firmware do roteador, se o exporter começar a falhar (`router_scrape_success = 0`) ou se métricas passarem a vir zeradas: um endpoint pode ter mudado de nome ou de formato.
- Ao querer coletar uma informação nova: procure na lista um endpoint candidato e consulte-o para ver o JSON. Foi assim que `macbind_info` foi encontrado.

**Como rodar** (a partir da raiz do repositório):
```shell
pip install -r requirements.txt
ROUTER_PASSWORD='sua-senha' python tools/discover.py
```
Ou num container, sem Python local, usando o `ROUTER_PASSWORD` do `.env`:
```shell
docker run --rm --env-file .env -v "$PWD":/app -w /app python:3.14-slim \
  sh -c "pip install -q -r requirements.txt && python tools/discover.py"
```

A saída contém o token de sessão (`stok=...`) e o `home.html` também; não publique nenhum dos dois. Para consultar um endpoint da lista, use o mesmo token: `curl "http://192.168.31.1/cgi-bin/luci/;stok=<token>/api/<endpoint>"`. A lista cobre só o que a página inicial referencia; APIs de outras telas podem estar nos arquivos `.js` listados (linhas `js:`).

## Testes
Os testes usam respostas fictícias do roteador (`tests/fixtures/`), sem acesso à rede, e rodam no GitHub Actions a cada PR e push na `main`:
```shell
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```
Sem Python local, rode num container:
```shell
docker run --rm -v "$PWD":/app -w /app python:3.14-slim \
  sh -c "pip install -q -r requirements.txt -r requirements-dev.txt && python -m pytest"
```
