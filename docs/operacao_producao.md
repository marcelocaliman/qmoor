# Operação — AncoPlat em produção

URL pública: **https://ancoplat.duckdns.org**

Servidor: DigitalOcean Droplet `ancoplat-prod`, IP `159.223.129.77`, Ubuntu 24.04 LTS.

---

## 1. Conectar ao servidor

```bash
# como root (operações privilegiadas)
ssh -i ~/.ssh/id_ancoplat root@159.223.129.77

# como usuário da aplicação (preferível para tarefas operacionais)
ssh -i ~/.ssh/id_ancoplat ancoplat@159.223.129.77
```

`PasswordAuthentication` está **off**. A única forma de entrar é com a chave `id_ancoplat` (sem passphrase) já cadastrada para os dois usuários.

> Se perder o acesso à chave, o droplet permite recuperação via console web do DigitalOcean (modo emergência). Não há outra rota.

## 2. Estado do app (status, processos, recursos)

```bash
# (root) status do backend
systemctl status ancoplat-api

# uptime, cpu, memória
htop

# espaço em disco (atenção a /opt/ancoplat/data e /opt/ancoplat/backups)
df -h /

# SSL e renovação
certbot certificates
systemctl status certbot.timer
```

## 3. Logs

```bash
# Backend (FastAPI/uvicorn) — journal estruturado
journalctl -u ancoplat-api -f               # tail em tempo real
journalctl -u ancoplat-api --since "1 hour ago"
journalctl -u ancoplat-api -n 200 --no-pager

# Logs do app (linha por execução do solver, ver logging_config.py)
tail -f /opt/ancoplat/logs/api.log

# Healthcheck (apenas falhas e restarts são gravados aqui)
tail -50 /opt/ancoplat/logs/healthcheck.log

# Backups (uma linha por execução do cron)
tail /opt/ancoplat/logs/backup.log

# nginx
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# fail2ban (IPs banidos por brute-force SSH)
sudo fail2ban-client status sshd
```

## 4. Atualizar o app (git pull + rebuild)

Com o repositório `marcelocaliman/ancoplat` atualizado no GitHub:

```bash
ssh -i ~/.ssh/id_ancoplat ancoplat@159.223.129.77
cd /opt/ancoplat/app

# Backend
git fetch origin
git reset --hard origin/main          # NOTA: descarta qualquer alteração local no servidor
venv/bin/pip install -r backend/requirements.txt    # idempotente

# Frontend
cd frontend
npm ci --legacy-peer-deps             # peer dep conflict openapi-typescript ↔ typescript
npm run build

# Recarrega o backend
sudo systemctl restart ancoplat-api

# nginx só precisa de reload se o arquivo de site mudou
sudo nginx -t && sudo systemctl reload nginx
```

`/opt/ancoplat/app/.env` **não está versionado** — o git reset não toca nele.

## 5. Rollback (deploy quebrou)

Identifique o commit anterior conhecido como bom (use `git log` ou o relatório de deploy original `c8e0d93` como baseline pós-renomeação):

```bash
ssh -i ~/.ssh/id_ancoplat ancoplat@159.223.129.77
cd /opt/ancoplat/app
git log --oneline -10                 # ver commits recentes
git reset --hard <SHA-bom>            # ex: c8e0d93
venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci --legacy-peer-deps && npm run build && cd ..
sudo systemctl restart ancoplat-api
```

Se o backend não subir, restaure o banco a partir do backup mais recente (próximo passo) e reinicie.

## 6. Restaurar backup do SQLite

Backups gerados às 03:00 -03 todo dia em `/opt/ancoplat/backups/ancoplat-YYYY-MM-DD.db.gz`. Retenção 30 dias.

```bash
ssh -i ~/.ssh/id_ancoplat ancoplat@159.223.129.77

# 1) Identificar e descomprimir o backup desejado
ls -la /opt/ancoplat/backups/
gunzip -k /opt/ancoplat/backups/ancoplat-2026-04-25.db.gz   # mantém o .gz original

# 2) Validar integridade do backup ANTES de substituir
sqlite3 /opt/ancoplat/backups/ancoplat-2026-04-25.db "PRAGMA integrity_check;"

# 3) Parar o backend
sudo systemctl stop ancoplat-api

# 4) Mover banco atual para .crash e colocar o backup no lugar
mv /opt/ancoplat/data/ancoplat.db /opt/ancoplat/data/ancoplat.db.crash
mv /opt/ancoplat/backups/ancoplat-2026-04-25.db /opt/ancoplat/data/ancoplat.db
chmod 640 /opt/ancoplat/data/ancoplat.db
chown ancoplat:ancoplat /opt/ancoplat/data/ancoplat.db

# 5) Subir backend
sudo systemctl start ancoplat-api
journalctl -u ancoplat-api -f       # confere startup limpo

# 6) Quando confirmar que está ok, remover o .crash
# (deixe alguns dias antes de apagar — pode conter dados que faltaram no backup)
```

Backup manual antes de operação delicada:

```bash
sudo -u ancoplat /opt/ancoplat/bin/backup.sh
```

## 7. Gerenciar usuários (basic auth)

Arquivo: `/etc/nginx/.htpasswd-ancoplat` (root:www-data, modo 640). Hash bcrypt cost 12.

```bash
# Adicionar usuário (a senha NÃO aparece em ps; é lida do stdin)
sudo htpasswd -iB -C 12 /etc/nginx/.htpasswd-ancoplat NOVO_USER <<'EOF'
SENHA_DO_USUARIO
EOF

# Trocar senha existente
sudo htpasswd -iB -C 12 /etc/nginx/.htpasswd-ancoplat USUARIO_EXISTENTE

# Remover usuário
sudo htpasswd -D /etc/nginx/.htpasswd-ancoplat USUARIO

# Listar usuários cadastrados (sem senhas)
sudo awk -F: '{print $1}' /etc/nginx/.htpasswd-ancoplat
```

`nginx` lê o arquivo em cada request — não precisa reload depois de editar.

## 8. SSL/HTTPS

```bash
# ver cert atual
certbot certificates

# renovar agora (force) — uso raro, o timer cuida automático
sudo certbot renew --force-renewal

# dry-run de renovação (não consome quota Let's Encrypt do certificado real)
sudo certbot renew --dry-run --no-random-sleep-on-renew

# se a renovação automática parar de funcionar, este timer mostra o problema:
systemctl status certbot.timer
journalctl -u certbot
```

Cert renova automaticamente 30 dias antes de expirar. nginx é recarregado pelo hook do certbot.

## 9. Backup, healthcheck e cron

```bash
# Cron registrado:
cat /etc/cron.d/ancoplat
# → 03:00 backup, */5 healthcheck

# Próximas execuções
sudo systemctl list-timers --all | grep -E "cron|certbot"

# Forçar backup manual
sudo -u ancoplat /opt/ancoplat/bin/backup.sh

# Forçar 1 healthcheck manual
sudo -u ancoplat /opt/ancoplat/bin/healthcheck.sh
echo "estado de falhas consecutivas: $(cat /opt/ancoplat/.healthcheck-fails)"
```

## 10. Firewall e segurança

```bash
# Ver regras UFW
sudo ufw status verbose

# fail2ban: ver IPs banidos atualmente
sudo fail2ban-client status sshd

# unban manual
sudo fail2ban-client set sshd unbanip 1.2.3.4
```

Atualizações de segurança rodam todo dia às 06:32 -03 via `unattended-upgrades` (apenas pacotes de `*-security`, sem auto-reboot).

## 11. Custos mensais

| Serviço | Custo |
|---|---|
| DigitalOcean Droplet (2 vCPU / 2 GB / 50 GB SSD / 2 TB transfer) | **US$ 12,00 / mês** |
| Domínio `ancoplat.duckdns.org` | grátis |
| Certificado TLS (Let's Encrypt) | grátis |
| Backup local em SSD | incluso no droplet |
| **Total** | **≈ US$ 12 / mês** (≈ R$ 60 / mês com câmbio atual) |

Se quiser dobrar de tamanho (4 GB / 80 GB), o plano vira **US$ 24 / mês**.

## 12. Variáveis de ambiente

Arquivo `/opt/ancoplat/app/.env` (NÃO versionado, perms 640 ancoplat:ancoplat):

```ini
ENVIRONMENT=production
DATABASE_URL=sqlite:////opt/ancoplat/data/ancoplat.db
LOG_LEVEL=INFO
LOG_FILE=/opt/ancoplat/logs/api.log
CORS_ALLOWED_ORIGINS=https://ancoplat.duckdns.org
```

Trocar valor → reiniciar com `sudo systemctl restart ancoplat-api`.

## 13. Estrutura de arquivos

```
/opt/ancoplat/
├── app/                  # repo clonado de github.com/marcelocaliman/ancoplat
│   ├── backend/
│   ├── frontend/dist/    # buildado pelo `npm run build`, servido pelo nginx
│   ├── venv/             # venv Python 3.12
│   └── .env              # variáveis de produção (NÃO versionadas)
├── data/                 # dados persistentes (perms 750)
│   └── ancoplat.db       # SQLite com 522 line_types + cases + executions
├── backups/              # SQLite backups diários (perms 750)
│   └── ancoplat-YYYY-MM-DD.db.gz
├── logs/
│   ├── api.log           # logs do FastAPI (rotacionado pelo Python + logrotate)
│   ├── healthcheck.log   # falhas e restarts auto
│   └── backup.log
└── bin/
    ├── backup.sh
    └── healthcheck.sh
```
