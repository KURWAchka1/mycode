#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALLER_VERSION="1.0.0"
readonly REPOSITORY="KURWAchka1/mycode"
readonly DEFAULT_REF="server-v${INSTALLER_VERSION}"
readonly SERVICE_NAME="playerok-monitor"
readonly SERVICE_USER="playerokmon"
readonly INSTALL_DIR="/opt/playerok-monitor"
readonly CONFIG_DIR="/etc/playerok-monitor"
readonly DATA_DIR="/var/lib/playerok-monitor"
readonly BACKUP_ROOT="/var/backups/playerok-monitor"
readonly NGINX_SITE="/etc/nginx/sites-available/playerok-monitor"
readonly ACME_ROOT="/var/www/playerok-monitor-acme"

ASSUME_YES=0
if [[ "${1:-}" == "--yes" ]]; then
  ASSUME_YES=1
elif [[ -n "${1:-}" ]]; then
  printf 'Использование: sudo bash %s [--yes]\n' "$0" >&2
  exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Запустите установщик от root: sudo bash %s\n' "$0" >&2
  exit 1
fi

umask 027
export DEBIAN_FRONTEND=noninteractive

TEMP_DIR="$(mktemp -d /tmp/playerok-monitor-install.XXXXXX)"
cleanup() { rm -rf -- "$TEMP_DIR"; }
trap cleanup EXIT

log() { printf '\n\033[1;36m[%s]\033[0m %s\n' "$SERVICE_NAME" "$*"; }
fail() { printf '\n\033[1;31mОшибка:\033[0m %s\n' "$*" >&2; exit 1; }

existing=0
if [[ -s "$CONFIG_DIR/playerok.token" && -s "$CONFIG_DIR/api.token" && -f "$CONFIG_DIR/playerok.env" ]]; then
  existing=1
fi

printf '\nPlayerok Monitor VPS installer %s\n' "$INSTALLER_VERSION"
printf 'Режим: %s\n' "$([[ "$existing" -eq 1 ]] && printf 'безопасное обновление' || printf 'чистая установка')"
printf 'VPN, Telegram-боты и другие каталоги в /opt не изменяются.\n'

if [[ "$existing" -eq 1 && "$ASSUME_YES" -ne 1 ]]; then
  read -r -p 'Сохранить текущие токены, базу, HTTPS-адрес и продолжить? [Y/n] ' answer
  case "${answer:-y}" in y|Y|yes|YES|д|Д|да|ДА) ;; *) printf 'Отменено.\n'; exit 0 ;; esac
fi

if [[ "$existing" -eq 0 && ! -t 0 ]]; then
  fail 'Для первой установки нужен интерактивный терминал: потребуется токен Playerok, адрес и e-mail для HTTPS.'
fi

public_host=""
cert_path=""
key_path=""
email=""

if [[ "$existing" -eq 1 && -f "$NGINX_SITE" ]]; then
  public_host="$(awk '$1 == "server_name" { gsub(/;/, "", $2); if ($2 != "_") { print $2; exit } }' "$NGINX_SITE")"
  cert_path="$(awk '$1 == "ssl_certificate" { gsub(/;/, "", $2); print $2; exit }' "$NGINX_SITE")"
  key_path="$(awk '$1 == "ssl_certificate_key" { gsub(/;/, "", $2); print $2; exit }' "$NGINX_SITE")"
fi

if [[ "$existing" -eq 0 ]]; then
  detected_ip="$(curl -4fsS --connect-timeout 5 --max-time 10 https://api.ipify.org 2>/dev/null || true)"
  printf '\nУкажите домен, A/AAAA-запись которого уже ведёт на этот VPS.\n'
  printf 'Публичный IP сервера: %s\n' "${detected_ip:-не определён}"
  read -r -p 'Домен (например monitor.example.com): ' public_host
  public_host="${public_host,,}"
  [[ "$public_host" =~ ^[a-z0-9.-]+$ && "$public_host" == *.* ]] || fail 'Нужен корректный домен без https:// и пути.'
  [[ ! "$public_host" =~ ^[0-9.]+$ ]] || fail 'Для новой установки укажите домен: так Android и Windows получат доверенный HTTPS-сертификат.'
  read -r -p 'E-mail для выпуска и продления HTTPS-сертификата: ' email
  [[ "$email" == *@*.* ]] || fail 'Некорректный e-mail.'
  read -r -s -p 'Токен Playerok (ввод скрыт): ' playerok_token
  printf '\n'
  [[ ${#playerok_token} -ge 32 ]] || fail 'Токен Playerok выглядит слишком коротким.'
fi

[[ -n "$public_host" ]] || fail 'Не удалось определить HTTPS-адрес из существующей конфигурации Nginx.'

log 'Устанавливаю системные зависимости'
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl nginx openssl python3 python3-pip python3-venv tar

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -m 0750 -o root -g "$SERVICE_USER" "$CONFIG_DIR"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA_DIR"
install -d -m 0755 -o root -g root "$INSTALL_DIR" "$INSTALL_DIR/app" "$ACME_ROOT"

if [[ "$existing" -eq 1 ]]; then
  timestamp="$(date -u +%Y%m%d-%H%M%S)"
  backup_dir="$BACKUP_ROOT/$timestamp"
  install -d -m 0700 -o root -g root "$backup_dir"
  cp -a -- "$CONFIG_DIR" "$backup_dir/config"
  cp -a -- "$INSTALL_DIR/app" "$backup_dir/app"
  if [[ -f "$DATA_DIR/orders.sqlite3" ]]; then
    cp -a -- "$DATA_DIR/orders.sqlite3" "$backup_dir/orders.sqlite3"
  fi
  if [[ -f "$NGINX_SITE" ]]; then
    cp -a -- "$NGINX_SITE" "$backup_dir/nginx-playerok-monitor"
  fi
  printf 'Резервная копия: %s\n' "$backup_dir"
fi

log 'Загружаю проверенный серверный пакет'
archive="$TEMP_DIR/source.tar.gz"
ref="${PLAYEROK_MONITOR_REF:-$DEFAULT_REF}"
archive_url="${PLAYEROK_MONITOR_ARCHIVE_URL:-https://github.com/${REPOSITORY}/archive/refs/tags/${ref}.tar.gz}"
curl -fL --retry 4 --retry-delay 2 --connect-timeout 20 --max-time 240 -o "$archive" "$archive_url"
tar -xzf "$archive" -C "$TEMP_DIR"
source_app="$(find "$TEMP_DIR" -mindepth 3 -maxdepth 3 -type d -path '*/server/app' -print -quit)"
source_requirements="$(find "$TEMP_DIR" -mindepth 3 -maxdepth 3 -type f -path '*/server/requirements.txt' -print -quit)"
[[ -n "$source_app" && -n "$source_requirements" ]] || fail 'В архиве нет server/app или server/requirements.txt.'
for required in main.py config.py db.py event_bus.py processor.py playerok_watcher.py playerok_raw.py relist.py auto_reply.py; do
  [[ -s "$source_app/$required" ]] || fail "В серверном пакете отсутствует $required"
done

if systemctl list-unit-files "$SERVICE_NAME.service" >/dev/null 2>&1; then
  systemctl stop "$SERVICE_NAME" || true
fi

install -m 0644 -o root -g root "$source_app"/*.py "$INSTALL_DIR/app/"
install -m 0644 -o root -g root "$source_requirements" "$INSTALL_DIR/requirements.txt"

if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip wheel setuptools
"$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -r "$INSTALL_DIR/requirements.txt"

if [[ "$existing" -eq 0 ]]; then
  printf '%s' "$playerok_token" > "$CONFIG_DIR/playerok.token"
  openssl rand -hex 32 > "$CONFIG_DIR/api.token"
  printf '%s\n' 'Ожидайте, пожалуйста. Продавец скоро приступит к выполнению Вашего заказа.' > "$CONFIG_DIR/auto-reply.txt"
fi
chmod 0640 "$CONFIG_DIR/playerok.token" "$CONFIG_DIR/api.token" "$CONFIG_DIR/auto-reply.txt"
chown root:"$SERVICE_USER" "$CONFIG_DIR/playerok.token" "$CONFIG_DIR/api.token" "$CONFIG_DIR/auto-reply.txt"

cat > "$CONFIG_DIR/playerok.env" <<'ENV'
PLAYEROK_TOKEN_FILE=/etc/playerok-monitor/playerok.token
API_TOKEN_FILE=/etc/playerok-monitor/api.token
POLL_HOST=127.0.0.1
POLL_PORT=8765
AUTO_REPLY_ENABLED=true
AUTO_REPLY_TEXT_FILE=/etc/playerok-monitor/auto-reply.txt
DATA_DIR=/var/lib/playerok-monitor
RETRY_INTERVAL_SECONDS=30
LOG_LEVEL=INFO
ENV
chmod 0640 "$CONFIG_DIR/playerok.env"
chown root:"$SERVICE_USER" "$CONFIG_DIR/playerok.env"

cat > "/etc/systemd/system/$SERVICE_NAME.service" <<'UNIT'
[Unit]
Description=Playerok order monitor and application API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=playerokmon
Group=playerokmon
WorkingDirectory=/opt/playerok-monitor
EnvironmentFile=/etc/playerok-monitor/playerok.env
ExecStart=/opt/playerok-monitor/.venv/bin/python -m app.main
Restart=always
RestartSec=3
Nice=5
MemoryHigh=220M
MemoryMax=320M
MemorySwapMax=128M
CPUQuota=50%
CPUWeight=50
TasksMax=64
LimitNOFILE=2048
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/playerok-monitor
ReadOnlyPaths=/etc/playerok-monitor /opt/playerok-monitor

[Install]
WantedBy=multi-user.target
UNIT

if [[ ! -s "$cert_path" || ! -s "$key_path" ]]; then
  log 'Получаю доверенный HTTPS-сертификат'
  apt-get install -y --no-install-recommends certbot
  cat > "$NGINX_SITE" <<HTTP_ONLY
server {
    listen 80;
    listen [::]:80;
    server_name $public_host;
    location ^~ /.well-known/acme-challenge/ { root $ACME_ROOT; default_type text/plain; }
    location / { return 404; }
}
HTTP_ONLY
  ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/playerok-monitor
  nginx -t
  systemctl enable --now nginx
  certbot certonly --webroot -w "$ACME_ROOT" -d "$public_host" \
    --non-interactive --agree-tos --email "$email" --keep-until-expiring
  cert_path="/etc/letsencrypt/live/$public_host/fullchain.pem"
  key_path="/etc/letsencrypt/live/$public_host/privkey.pem"
fi

[[ -s "$cert_path" && -s "$key_path" ]] || fail 'HTTPS-сертификат не найден после настройки.'

cat > "$NGINX_SITE" <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $public_host;
    access_log off;
    location ^~ /.well-known/acme-challenge/ { root $ACME_ROOT; default_type text/plain; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $public_host;
    access_log off;
    ssl_certificate $cert_path;
    ssl_certificate_key $key_path;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 8k;

    location = /health {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8765;
        proxy_connect_timeout 3s; proxy_read_timeout 10s; proxy_buffering off;
    }
    location = /cursor {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8765;
        proxy_connect_timeout 3s; proxy_read_timeout 10s; proxy_buffering off;
    }
    location = /poll {
        limit_except GET POST { deny all; }
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_connect_timeout 3s; proxy_read_timeout 70s; proxy_send_timeout 10s;
        proxy_buffering off; proxy_request_buffering off;
    }
    location = /relist {
        limit_except GET POST { deny all; }
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_connect_timeout 3s; proxy_read_timeout 60s; proxy_send_timeout 10s;
        proxy_buffering off; proxy_request_buffering off;
    }
    location = /wake {
        limit_except POST { deny all; }
        proxy_pass http://127.0.0.1:8765;
        proxy_connect_timeout 3s; proxy_read_timeout 30s; proxy_send_timeout 10s;
        proxy_buffering off; proxy_request_buffering off;
    }
    location = /fulfill {
        limit_except POST { deny all; }
        proxy_pass http://127.0.0.1:8765;
        proxy_connect_timeout 3s; proxy_read_timeout 45s; proxy_send_timeout 10s;
        proxy_buffering off; proxy_request_buffering off;
    }
    location = /test {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8765;
        proxy_connect_timeout 3s; proxy_read_timeout 10s; proxy_buffering off;
    }
    location / { return 404; }
}
NGINX

ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/playerok-monitor
nginx -t
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl reload nginx

log 'Проверяю сервис и локальный API'
api_token="$(tr -d '\r\n' < "$CONFIG_DIR/api.token")"
healthy=0
for _ in {1..30}; do
  if curl -fsS --get --max-time 3 --data-urlencode "token=$api_token" "http://127.0.0.1:8765/health" >/dev/null; then
    healthy=1
    break
  fi
  sleep 1
done
if [[ "$healthy" -ne 1 ]]; then
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager >&2 || true
  fail 'Сервис запущен, но не прошёл health-check. Журнал показан выше; резервная копия сохранена.'
fi

systemctl is-active --quiet "$SERVICE_NAME" || fail 'systemd не считает сервис активным.'

printf '\n\033[1;32mУстановка завершена.\033[0m\n'
printf 'Версия установщика: %s\n' "$INSTALLER_VERSION"
printf 'Python: %s\n' "$("$INSTALL_DIR/.venv/bin/python" --version 2>&1)"
printf 'Сервис: active; лимиты VPS: CPU 50%%, RAM 320 MB\n'
printf '\nPairing URL для Android и Windows:\n\033[1mhttps://%s/poll?token=%s\033[0m\n' "$public_host" "$api_token"
printf '\n1. Скопируйте URL целиком в настройки приложения.\n'
printf '2. Нажмите проверку подключения, затем включите мониторинг.\n'
printf '3. Повторный запуск этого файла обновит код, но сохранит URL, токены, сообщения и базу.\n'
printf '4. Диагностика: systemctl status %s; journalctl -u %s -f\n' "$SERVICE_NAME" "$SERVICE_NAME"
