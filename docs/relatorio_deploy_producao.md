# Relatório — Deploy de produção AncoPlat

Data: 2026-04-25
Executor: deploy automatizado em sessão única (commit baseline `c8e0d93`).

## 1. Sumário executivo

A aplicação **AncoPlat** está rodando em produção no domínio público https://ancoplat.duckdns.org com TLS válido (Let's Encrypt ECDSA), autenticação Basic via nginx (bcrypt cost 12) e backend FastAPI gerenciado pelo systemd. O catálogo legado (522 entradas legacy_qmoor) e o histórico de cases (3 casos + 12 execuções + 2 mooring systems) foram migrados intactos da máquina local — checksum SHA-256 verificado byte-a-byte. Backups diários automáticos, healthcheck a cada 5 min com restart automático em caso de falha consecutiva, atualizações de segurança automáticas (unattended-upgrades), firewall UFW + fail2ban contra brute-force SSH.

Métricas de prontidão:
- 282/282 testes verde, mantidos após refator de configuração env-driven.
- Latência server-side: 1-10 ms para endpoints típicos (`/health`, `/cases`, `/line-types`).
- Pipeline end-to-end validado: `POST /cases` → 201, `POST /cases/{id}/solve` → 200 `converged`, `GET /cases/{id}/export/pdf` → 200 PDF v1.4 89 KB.
- Renovação automática de SSL: dry-run ✅.

## 2. URLs e usuários

| | |
|---|---|
| URL pública | https://ancoplat.duckdns.org |
| Healthcheck público | https://ancoplat.duckdns.org/api/v1/health |
| OpenAPI / Swagger | https://ancoplat.duckdns.org/api/v1/docs |
| Usuários (basic auth) | `caliman_ap`, `UserTest` |
| Senhas | armazenadas apenas como hash bcrypt em `/etc/nginx/.htpasswd-ancoplat`. **Comunicadas fora deste relatório.** |

Restrição: tudo atrás do basic auth. Sem credenciais → HTTP 401. Toda a aplicação é HTTPS-only (HTTP 80 redireciona 301 para HTTPS).

## 3. Infraestrutura

| | |
|---|---|
| Provider | DigitalOcean (Droplet) |
| Hostname | `ancoplat-prod` |
| IP público | `159.223.129.77` |
| Domínio | `ancoplat.duckdns.org` (DuckDNS, gratuito) |
| Sistema | Ubuntu 24.04.3 LTS (kernel 6.8.0-71) |
| vCPU / RAM / Disco | 2 vCPU / 2 GB RAM / 50 GB SSD / 2 TB transfer |
| Swap | 2 GB em `/swapfile` (`vm.swappiness=10`) |
| Timezone | `America/Sao_Paulo` |

## 4. Configuração

### 4.1 systemd (`/etc/systemd/system/ancoplat-api.service`)

uvicorn com 2 workers em `127.0.0.1:8000`. `Restart=on-failure`, `RestartSec=5`, `StartLimitBurst=5/60s`. Hardening: `NoNewPrivileges`, `ProtectSystem=strict` com `ReadWritePaths` apenas em `/opt/ancoplat/{data,logs,app}`, `PrivateTmp`, `ProtectHome`, `ProtectKernelTunables`, `RestrictSUIDSGID`. Logs vão pro journal com identifier `ancoplat-api`.

### 4.2 nginx (`/etc/nginx/sites-available/ancoplat`)

- TLS 1.2+1.3, cipher suite ECDHE-only (P-256/X25519), session cache 10m.
- HTTP/2 ativo (sintaxe combinada `listen 443 ssl http2;` por estarmos em nginx 1.24).
- Security headers (`always`): `Strict-Transport-Security` (2 anos, includeSubDomains), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (geo/mic/cam negadas).
- Compressão gzip nível 6 para HTML/CSS/JS/JSON/SVG/font, mínimo 1024 bytes.
- `client_max_body_size 2m;` em todas as rotas.
- Frontend SPA servido de `/opt/ancoplat/app/frontend/dist`. Assets `/assets/*` com `Cache-Control: public, immutable, expires 1y` (Vite gera nomes content-hashed).
- Reverse proxy `/api/` → `http://127.0.0.1:8000` com timeouts connect=10 s, read/send=60 s.
- Rate limit defensivo `10 r/s burst 20` em `/api/`.
- Redirect HTTP→HTTPS (301), exceto `/.well-known/acme-challenge/` que fica acessível sem TLS para renovação certbot.

### 4.3 certbot

- Cert ECDSA P-256, emitido por Let's Encrypt E7, válido 89 dias (2026-04-25 → 2026-07-24).
- Conta `e574ace0d429fadf224451df9d8c6bef`, e-mail de contato `marcelo.salgado.caliman@gmail.com`.
- Renovação via `certbot.timer` (próxima execução automática 06:23 -03 diariamente — random delay até 8 min interno).
- Webroot em `/var/www/html`, sem auth nessa rota.
- Dry-run `certbot renew --dry-run --no-random-sleep-on-renew`: ✅ success.

### 4.4 Autenticação

`/etc/nginx/.htpasswd-ancoplat` (root:www-data, 640) com 2 usuários, hash bcrypt `$2y$12$...`. nginx valida no Basic Auth global (declaração no `server` block), exceto challenge ACME.

### 4.5 Firewall

UFW: `default deny incoming`, allow `22/tcp`, `80/tcp`, `443/tcp` (v4 e v6). fail2ban com jail `sshd` em modo `aggressive`, bantime 1 h, maxretry 5, backend systemd.

## 5. Aplicação

### 5.1 Refactor introduzido (commit `c8e0d93`)

- `backend/api/config.py`: novo módulo, lê `.env` via python-dotenv (opcional) e expõe `DATABASE_URL`, `DB_PATH`, `LOG_FILE`, `LOG_LEVEL`, `ENVIRONMENT`, `CORS_ALLOWED_ORIGINS`.
- `backend/api/db/session.py`: importa de `config` em vez de hardcodar `backend/data/ancoplat.db`.
- `backend/api/logging_config.py`: usa `LOG_FILE`/`LOG_LEVEL` do config.
- `backend/api/main.py`: CORS allow_origins lê do config.
- `backend/requirements.txt`: + `python-dotenv`.
- 1 teste atualizado (`test_log_arquivo_rotativo_existe`) para monkeypatch `LOG_FILE` em vez de `DB_PATH`.

Comportamento em desenvolvimento local **inalterado** (defaults batem com paths antigos). Suíte 282/282.

### 5.2 Banco de dados

| | |
|---|---|
| Arquivo | `/opt/ancoplat/data/ancoplat.db` |
| Tamanho | 14.987.264 bytes (≈ 14,3 MB) |
| Origem | scp da máquina local (commit `d7cdfb9` baseline) |
| SHA-256 | `bee967a0f41ef97f563e8d449bdf29e652635205ad1faa09eed55cb3d130508d` (idêntico em local + servidor) |
| `PRAGMA integrity_check` | `ok` |
| `line_types` | 522 (catálogo legacy_qmoor 100% importado) |
| `cases` | 3 |
| `executions` | 12 |
| `mooring_systems` | 2 |
| Permissões | `640` `ancoplat:ancoplat` (legível só pelo grupo, dir pai 750) |

### 5.3 Frontend

Build no servidor com `npm ci --legacy-peer-deps` (peer dep conflict `openapi-typescript@7 ↔ typescript@6` que não aparece localmente porque `node_modules/` já estava resolvido). `dist/` final 6.8 MB. `frontend/src/api/client.ts` usa `API_BASE_URL = '/api/v1'` (path relativo) — nginx serve frontend e API no mesmo origin, então `VITE_API_BASE_URL` não foi necessário. Domínio futuro pode ser trocado sem rebuild.

## 6. Observabilidade e rotinas

### 6.1 Backup

- `/opt/ancoplat/bin/backup.sh` rodando às 03:00 -03 via `/etc/cron.d/ancoplat`.
- Usa `sqlite3 ".backup"` (Online Backup API), seguro mesmo com app escrevendo.
- Compressão gzip → ~5,6 MB por backup (60 % de compactação no DB de 14 MB).
- Retenção 30 dias (`find -mtime +30 -delete`).
- Validação automática `gunzip -t` após criar.
- Log em `/opt/ancoplat/logs/backup.log`.

### 6.2 Healthcheck

- `/opt/ancoplat/bin/healthcheck.sh` rodando a cada 5 min.
- Falha = 1 try com timeout 10 s no `http://127.0.0.1:8000/api/v1/health`.
- Após **2 falhas consecutivas** → `sudo systemctl restart ancoplat-api`.
- Estado em `/opt/ancoplat/.healthcheck-fails`. Reset em `recovered`.
- Log em `/opt/ancoplat/logs/healthcheck.log` (apenas falhas, recoveries e restarts; runs ok são silenciosos).
- Validado com teste destrutivo: stop → 2 falhas → restart automático em ~5 s → recovery.

### 6.3 Logrotate

`/etc/logrotate.d/ancoplat` rotaciona `/opt/ancoplat/logs/*.log` semanalmente, mantém 4 semanas, comprime, `copytruncate` (preserva inode pra Python `RotatingFileHandler` continuar escrevendo).

### 6.4 unattended-upgrades

Atualizações de segurança automáticas (apenas `*-security`), sem auto-reboot. Timer `apt-daily-upgrade` ~06:32 -03 diariamente.

## 7. Comandos úteis para operação

Documentação completa em [`docs/operacao_producao.md`](operacao_producao.md). Resumo:

| Tarefa | Comando |
|---|---|
| Status do backend | `systemctl status ancoplat-api` |
| Logs ao vivo | `journalctl -u ancoplat-api -f` |
| Update do app | `cd /opt/ancoplat/app && git pull && cd frontend && npm ci --legacy-peer-deps && npm run build && cd .. && sudo systemctl restart ancoplat-api` |
| Rollback | `git reset --hard <SHA>` + reinstall + restart |
| Backup manual | `sudo -u ancoplat /opt/ancoplat/bin/backup.sh` |
| Restore | parar serviço → `mv backup over /opt/ancoplat/data/ancoplat.db` → restart |
| Trocar senha de usuário | `sudo htpasswd -iB -C 12 /etc/nginx/.htpasswd-ancoplat USER` (senha via stdin) |
| Listar IPs banidos | `sudo fail2ban-client status sshd` |

## 8. Custos mensais

| Item | Custo |
|---|---|
| DigitalOcean Droplet 2 vCPU / 2 GB / 50 GB / 2 TB | **US$ 12 / mês** |
| Domínio `ancoplat.duckdns.org` | grátis |
| Cert TLS (Let's Encrypt) | grátis |
| Backup local | incluso |
| **Total** | **≈ US$ 12 / mês (≈ R$ 60)** |

## 9. Próximos passos sugeridos

1. **Backup off-site.** Hoje os backups vivem no mesmo droplet. Se o disco corromper, perdemos tudo. Sugestão: rsync diário para um bucket S3/Spaces (DigitalOcean Spaces a US$ 5/mês cobre 250 GB) ou um backup `restic` para o próprio Mac do usuário.
2. **Monitoring externo.** Healthcheck interno detecta crash, mas não detecta o droplet ficando sem internet ou sem disco. UptimeRobot (free tier) ou cron@local Mac batendo o `/health` cobre. Custo zero.
3. **Code-splitting do frontend.** O bundle `plotly-vendor.js` está em 4,6 MB (1,4 MB gzip). Lazy-load só nas páginas que usam Plotly reduz first paint pra usuários com link lento. Mudança pequena no `vite.config.ts`.
4. **CI/CD básico.** GitHub Actions rodando os testes do backend a cada push e (opcional) auto-deploy em main com SSH key. Hoje deploy é manual.
5. **CSP completo.** Em D6 deixei só headers seguros não-CSP (HSTS, X-Frame-Options, etc.) porque um CSP estrito pode quebrar Plotly/React inline. Pode ser feito incrementalmente com `Content-Security-Policy-Report-Only` antes de aplicar.
6. **Autenticação melhor que Basic Auth.** Funciona, mas: (a) sem logout limpo (precisa fechar browser), (b) sem mecanismo de "esqueci a senha", (c) credenciais transitam em todo request. Migrar para sessão FastAPI + cookie httponly é tarefa de meio dia se virar incômodo.
7. **Pendência da auditoria F1a:** anomalia μ R5Studless = 0,6 vs R4Studless = 1,0 ainda aguarda validação do engenheiro revisor (pendência registrada em CLAUDE.md).
