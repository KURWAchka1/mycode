# Playerok Monitor VPS

Сервер принимает события Playerok, хранит заказы в SQLite и предоставляет один HTTPS API для Android и Windows. Установщик рассчитан на Debian/Ubuntu VPS с `systemd` и Nginx.

## Установка

1. Скачайте `install-playerok-monitor.sh` из релиза `server-v1.0.0`.
2. Перенесите файл на VPS и запустите:

   ```bash
   sudo bash install-playerok-monitor.sh
   ```

3. При первой установке введите домен, e-mail для Let's Encrypt и токен Playerok. В конце скрипт выведет готовый Pairing URL.

Повторный запуск выполняет обновление: ставит зависимости, делает резервную копию, сохраняет SQLite, токены, сообщения, HTTPS-сертификат и Pairing URL. Для подтверждённого обновления без вопроса используйте `sudo bash install-playerok-monitor.sh --yes`.

Установщик работает только с `/opt/playerok-monitor`, `/etc/playerok-monitor`, `/var/lib/playerok-monitor`, своим unit-файлом и своим Nginx site. VPN, Telegram-боты и другие сервисы не изменяются.

## Проверка

```bash
systemctl status playerok-monitor
journalctl -u playerok-monitor -f
```

Сервис ограничен 50% CPU и 320 MB RAM. Фоновое получение полей покупателя использует одноразовое дозаполнение и не создаёт постоянную нагрузку на VPS.
