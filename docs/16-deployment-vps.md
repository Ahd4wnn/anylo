# 16 · Deployment (VPS, no Docker)

A single Ubuntu 24.04 LTS VPS in an India region runs everything for v1 (≈ up to 2,000 shops). Everything below is plain packages + systemd + nginx.

## 1. Server layout

| Item | Value |
|---|---|
| Size to start | 4 vCPU, 8 GB RAM, 160 GB SSD |
| Users | `anylo` (app runtime, no shell login), `deploy` (CI SSH, sudo limited to restart units) |
| Code | `/srv/anylo/releases/<git-sha>/` with `/srv/anylo/current` → symlink |
| Python venv | `/srv/anylo/venv/<git-sha>` |
| Env | `/etc/anylo/anylo.env` (0640 root:anylo) |
| Media | `/var/lib/anylo/media` |
| Backups | `/var/backups/anylo` (local), plus off-box copies |
| Logs | journald (`journalctl -u anylo-api`) |

## 2. Packages

```bash
apt install -y nginx postgresql-16 postgresql-contrib python3.12 python3.12-venv \
  certbot python3-certbot-nginx ufw fail2ban unattended-upgrades \
  libpango-1.0-0 libpangoft2-1.0-0 fonts-noto-core fonts-noto-ui-core   # WeasyPrint + Indic fonts
```

Node is only needed on the CI runner. The web app is built in CI and uploaded as static files.

## 3. PostgreSQL

```sql
CREATE ROLE anylo_owner LOGIN PASSWORD :'owner_pw';         -- migrations
CREATE ROLE anylo_app   LOGIN PASSWORD :'app_pw' NOSUPERUSER NOBYPASSRLS;
CREATE DATABASE anylo OWNER anylo_owner;
\c anylo
CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

- `backend/scripts/setup_roles.sql` takes passwords as `psql -v` variables. **No passwords in git.**
- Postgres listens on localhost only. Tune with `pgtune`. `statement_timeout=15s` for `anylo_app`.

## 4. systemd units

`/etc/systemd/system/anylo-api.service`:
```ini
[Unit]
Description=Anylo API
After=network.target postgresql.service

[Service]
User=anylo
Group=anylo
EnvironmentFile=/etc/anylo/anylo.env
WorkingDirectory=/srv/anylo/current/backend
ExecStart=/srv/anylo/current/venv/bin/gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker -w 4 -b 127.0.0.1:8000 \
  --graceful-timeout 30 --timeout 120 --access-logfile -
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/anylo/media
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`anylo-worker.service` is the same, but runs `ExecStart=/srv/anylo/current/venv/bin/python -m app.worker.main`. It is a single instance.

Using `HUP` with gunicorn gives **graceful reloads**: no dropped requests during deploys, which fixes a PlantBill limitation.

## 5. nginx

```nginx
limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;

server {
  server_name anylo.in www.anylo.in;
  root /srv/anylo/current/web/dist;
  location / { try_files $uri /index.html; }
  location /assets/ { expires 1y; add_header Cache-Control "public, immutable"; }
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://checkout.razorpay.com; frame-src https://api.razorpay.com https://checkout.razorpay.com; connect-src 'self' https://api.anylo.in https://lumberjack.razorpay.com; img-src 'self' data: blob: https://api.anylo.in; style-src 'self' 'unsafe-inline'" always;
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
  add_header X-Content-Type-Options nosniff always;
  add_header Referrer-Policy strict-origin-when-cross-origin always;
}

server {
  server_name api.anylo.in;
  client_max_body_size 12m;
  location /v1/auth/ { limit_req zone=auth burst=5 nodelay; proxy_pass http://127.0.0.1:8000; include proxy_params; }
  location /v1/ai/   { proxy_pass http://127.0.0.1:8000; include proxy_params; proxy_buffering off; proxy_read_timeout 90s; }  # SSE
  location /         { proxy_pass http://127.0.0.1:8000; include proxy_params; }
  location /_media/  { internal; alias /var/lib/anylo/media/; }   # served via X-Accel-Redirect after auth check
}
```

Get certificates with `certbot --nginx -d anylo.in -d www.anylo.in -d api.anylo.in`. Renewal is handled by the systemd timer. The firewall (`ufw`) allows only 22, 80 and 443. fail2ban watches sshd and nginx 401/429 bursts.

## 6. Deploy (CI-driven, from GitHub Actions on tag `v*` or manual dispatch)

1. CI builds `web/dist` and runs every test.
2. It rsyncs the release to `/srv/anylo/releases/<sha>/` (backend source + web/dist).
3. On the server:
   1. Create a venv for the release and `pip install -r requirements.lock`.
   2. `pg_dump -Fc anylo > /var/backups/anylo/pre-<sha>.dump`
   3. `alembic upgrade head` (as `anylo_owner`). **Migrations must be backward compatible with the previous release** (expand → deploy → contract).
   4. `ln -sfn` current → the new release.
   5. `systemctl reload anylo-api`
   6. `systemctl restart anylo-worker`
   7. Smoke test `curl -fsS https://api.anylo.in/v1/health`. On failure, run the rollback script: re-point the symlink, reload, and restore the DB dump only if a migration ran and is not reversible.
4. Keep the last 5 releases.

`scripts/deploy.sh` and `scripts/rollback.sh` live in the repo. Staging is a second, smaller VPS (`staging.anylo.in`) deployed from `main` automatically. Production deploys only from tags.

## 7. Backups and monitoring

- Nightly `pg_dump -Fc` plus a weekly media tarball, encrypted with `age` and pushed to off-box object storage (S3-compatible, Mumbai region). Retention: 14 daily, 8 weekly, 12 monthly.
- **Restore drill every month** on staging (documented checklist).
- Optional WAL archiving with `pgBackRest` once there are more than 500 paying shops.
- Uptime: an external check on `/v1/health` every minute → alert email/Telegram.
- Error tracking: Sentry (self-hosted not required; SaaS free tier) for the API and web, with PII scrubbing.
- Metrics: request rate, p95 latency and the 5xx count, read from the gunicorn access log with GoAccess; or later, `prometheus-fastapi-instrumentator` + Grafana Cloud free tier.
- Disk, CPU and memory alerts via `netdata` or the provider's monitoring.

## 8. Local development (Windows/macOS/Linux, no Docker)

1. Install PostgreSQL 16 locally and run `psql -f backend/scripts/setup_roles.sql -v owner_pw=dev -v app_pw=dev`.
2. In `backend`:
   ```
   python -m venv .venv
   pip install -r requirements-dev.txt
   cp .env.example .env
   alembic upgrade head
   python -m app.scripts.seed_demo
   uvicorn app.main:app --reload
   ```
3. Run `python -m app.worker.main` in a second terminal.
4. In `web`: `npm ci && npm run dev`.
5. Android: run the `devDebug` flavor against `10.0.2.2:8000`.
6. Razorpay: use test keys plus `ngrok http 8000` (or Cloudflare Tunnel) for webhooks.
