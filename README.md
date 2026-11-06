# Monitor WAN – Xiaomi BE6500

Exporter Python que faz login na interface web do roteador (`192.168.31.1`), coleta o status do multiwan/WANs e expõe em formato Prometheus. A stack (exporter + Prometheus + Grafana) sobe via Docker Compose.

## Uso
```
cp .env.example .env   # preencha ROUTER_PASSWORD (senha do WiFi)
docker compose up -d --build
```
Grafana: http://localhost:3000 (admin/admin por padrão) → dashboard "Xiaomi BE6500 - WANs".

![Dashboard WAN](./docs/images/WAN-dashboard.png)

Clientes da LAN (velocidade, consumo e tempo conectado) ficam no dashboard "Xiaomi BE6500 - LAN (clientes)":

![Dashboard LAN](./docs/images/LAN-dashboard.png)

## Endpoints do roteador usados
- `api/misystem/get_ps_service?service=multiwan` – habilitado, política, WAN ativa, pesos
- `api/xqnetwork/get_wan_status` – IPv4/IPv6 da WAN principal
- `api/xqnetwork/pppoe_status?wan_name=WAN1|WAN2` – status/erro/velocidade de cada WAN

`tools/discover.py` lista as APIs que a página principal usa (útil se o firmware mudar).

## Alertas no Telegram (atualmente DESATIVADO)
Para ativar: `rm grafana/provisioning/alerting/telegram-off.yml && mv grafana/provisioning/alerting/telegram.yml.disabled grafana/provisioning/alerting/telegram.yml`, depois siga os passos abaixo.

1. Crie um bot com o `@BotFather` e copie o token.
2. Mande uma mensagem ao bot (ou adicione-o ao grupo) e obtenha o chat id em `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. Preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env` e rode `docker compose up -d`.
