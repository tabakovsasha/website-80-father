# 80 лет Петру Табакову

## Архитектура

Это маленькое однокомпонентное веб-приложение для слайд-шоу. Оно:

- слушает HTTP на `0.0.0.0:8080`;
- обслуживает статический сайт из `web/`;
- автоматически находит все WebP-файлы в `web/images/`;
- возвращает список слайдов через JSON API;
- обслуживает только сайт и slide API на `0.0.0.0:8080`;
- отправляет аналитику через внутренний proxy в отдельный localhost-сервис на `127.0.0.1:8081`.

В production приложение работает на `prod-app-01`. Внешний HTTPS и reverse proxy выполняет Caddy на отдельной VM:

```text
Браузер -> HTTPS -> Caddy -> HTTP prod-app-01:8080 -> website-80-father.service
```

## Структура проекта

- `app.py` — HTTP-сервис сайта и slide API;
- `analytics_service.py` — localhost analytics backend and SQLite logic;
- `web/index.html` — основная страница слайд-шоу;
- `web/css/style.css` — стили отображения;
- `web/js/viewer.js` — клиентская логика навигации и аналитики;
- `web/images/` — каталог со слайдами в формате WebP;
- `scripts/analytics_cli.py` — CLI для статистики;
- `systemd/website-80-father.service` — unit сайта;
- `systemd/petr80-analytics.service` — unit аналитики;

## Слайды

Слайды автоматически обнаруживаются в `web/images/`:

- берутся только файлы с расширением `.webp`;
- сортировка выполняется по имени файла;
- порядок соответствует детерминированному списку, который возвращает сервер;
- на фронтенде используется порядок из API, а не отдельная JavaScript-сортировка.

Чтобы добавить или удалить слайды, просто измените содержимое `web/images/` и перезапустите сервис.

## Установка с нуля

Команды ниже рассчитаны на Debian/Ubuntu и путь `/opt/website-80-father`.

### 1. Установить зависимости и скопировать проект

```bash
sudo apt update
sudo apt install -y python3
sudo mkdir -p /opt/website-80-father
sudo cp -a ./ /opt/website-80-father/
cd /opt/website-80-father
```

Если проект копируется через `scp`, выполняйте копирование с локального компьютера:

```bash
scp -r /path/to/website-80-father user@SERVER:/tmp/
ssh user@SERVER
sudo mv /tmp/website-80-father /opt/website-80-father
```

Проверить, что слайды на месте:

```bash
find /opt/website-80-father/web/images -type f -iname '*.webp' | wc -l
```

### 2. Установить systemd units

Сайт слушает `0.0.0.0:8080`. Analytics слушает только `127.0.0.1:8081`.

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin petr80-analytics 2>/dev/null || true
sudo install -d -o petr80-analytics -g petr80-analytics /var/lib/petr80-analytics
sudo chown -R petr80-analytics:petr80-analytics /var/lib/petr80-analytics
sudo cp /opt/website-80-father/systemd/website-80-father.service /etc/systemd/system/
sudo cp /opt/website-80-father/systemd/petr80-analytics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now website-80-father.service
sudo systemctl enable --now petr80-analytics.service
```

`enable` добавляет автозапуск после reboot, `--now` запускает units сразу.
`chown` нужен, чтобы analytics-пользователь мог писать в SQLite после переноса базы или восстановления backup.

### 3. Проверить запуск

```bash
systemctl is-active website-80-father.service
systemctl is-active petr80-analytics.service
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/api/slides
curl http://127.0.0.1:8081/healthz
ss -ltn | grep -E ':8080|:8081'
```

Ожидаемые listeners:

```text
0.0.0.0:8080    website-80-father.service
127.0.0.1:8081  petr80-analytics.service
```

`petr80-analytics.service` не должен быть доступен извне. `website-80-father.service` принимает `/analytics/*` на `8080` и внутренне передаёт запросы на `127.0.0.1:8081`.

### 4. Настроить внешний Caddy

Caddy работает на отдельной VM и проксирует внешний HTTPS-запрос на `prod-app-01:8080`. Конфигурация Caddy находится вне этого репозитория и здесь не требуется.

После перезагрузки сервера проверить ещё раз:

```bash
sudo reboot
# после reconnect:
systemctl is-active website-80-father.service petr80-analytics.service
```

## Управление сервисами

```bash
sudo systemctl status website-80-father.service
sudo systemctl status petr80-analytics.service
sudo systemctl restart website-80-father.service
sudo systemctl restart petr80-analytics.service
sudo journalctl -u website-80-father.service -f
sudo journalctl -u petr80-analytics.service -f
```

## Полностью остановить сервисы

Чтобы остановить сайт и analytics и запретить их автоматический запуск после reboot:

```bash
sudo systemctl disable --now website-80-father.service
sudo systemctl disable --now petr80-analytics.service
```

Проверка:

```bash
systemctl is-active website-80-father.service petr80-analytics.service
ss -ltn | grep -E ':8080|:8081' || true
```

Эти команды не останавливают внешний Caddy на отдельной VM.

## Веб-сайт

После запуска приложение доступно по адресу:

```text
http://0.0.0.0:8080/
```

Через Caddy на отдельной VM сайт доступен по публичному HTTPS-домену.

## Analytics

`website-80-father.service` принимает публичные запросы на `0.0.0.0:8080`, включая `/analytics/*`, и проксирует analytics внутри процесса на `127.0.0.1:8081`. nginx на `prod-app-01` не требуется. Не запускайте nginx на `:8080` одновременно с `website-80-father.service`.

Anonymous visitors are stored in SQLite at:

```text
/var/lib/petr80-analytics/analytics.db
```

The browser stores random `crypto.randomUUID()` visitor IDs in `localStorage`, creates a new session ID per page load, and sends only active slide views. Duplicate slide views do not increase completion.

CLI:

```bash
python3 /opt/website-80-father/scripts/analytics_cli.py
python3 /opt/website-80-father/scripts/analytics_cli.py --json
```

## Резервное копирование и сброс аналитики

Backup:

```bash
sudo cp /var/lib/petr80-analytics/analytics.db /var/lib/petr80-analytics/analytics.db.bak
```

Reset/delete all analytics data:

```bash
sudo rm /var/lib/petr80-analytics/analytics.db
sudo mkdir -p /var/lib/petr80-analytics
sudo chown -R petr80-analytics:petr80-analytics /var/lib/petr80-analytics
sudo systemctl restart petr80-analytics.service
```

Полностью обнулить статистику безопасно можно так:

```bash
sudo systemctl stop petr80-analytics.service
sudo rm -f /var/lib/petr80-analytics/analytics.db \
	/var/lib/petr80-analytics/analytics.db-wal \
	/var/lib/petr80-analytics/analytics.db-shm
sudo install -d -o petr80-analytics -g petr80-analytics /var/lib/petr80-analytics
sudo systemctl start petr80-analytics.service
```

После этого база создастся заново, а visitors, visits и slide views будут равны нулю. Слайд-шоу и файлы изображений не изменятся.

## Примечания

- Аналитика асинхронная и не должна блокировать показ слайдов.
- Ошибки аналитики не останавливают работу сайта.
- Файлы в `web/images/` не жёстко зашиты в код и не фиксированы в JavaScript.
- Вся логика основана на фактическом содержимом директории.
