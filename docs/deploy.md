# Deploying Winnow

One server runs everything: `docker-compose.prod.yml` starts these services:

- **Caddy:** HTTPS and security headers.
- **The API:** Uvicorn, several workers.
- **The background worker.**
- **PostgreSQL** and **Redis.**
- **ClamAV:** scans uploaded PDFs.
- **The built web app**, served by nginx.

Only Caddy is reachable from outside, on ports 80 and 443.

## What you need

- **A server** with at least 2 vCPUs, 4 GB of memory and 40 GB of SSD. Any Linux with
  Docker Engine 24+ and the Compose plugin will do.
- **A domain name** whose A (and AAAA) record points at the server, for example
  `winnow.example.org`.
- **Ports 80 and 443 open**, TCP and UDP. Caddy uses port 80 to prove it controls the
  domain when it gets the certificate, and UDP 443 for HTTP/3.
- **An SMTP account for Winnow's email:** sign-up confirmation, password resets,
  invitations and digests. Without one, nobody can confirm an email address.

## First start

```bash
git clone https://github.com/asifuddin01/WINNOW.git winnow && cd winnow
cp .env.example .env && chmod 600 .env
```

Edit `.env`. These must be set for production:

| Setting | Value |
| --- | --- |
| `WINNOW_ENV` | `production` |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | `openssl rand -base64 32` (encrypts two-factor secrets; keep a copy with your backups) |
| `POSTGRES_PASSWORD` | `openssl rand -hex 16` |
| `DATABASE_URL` | `postgresql+asyncpg://winnow:<POSTGRES_PASSWORD>@db:5432/winnow` |
| `PUBLIC_URL` | `https://winnow.example.org` |
| `SITE_ADDRESS` | `winnow.example.org` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | your mail provider's |

Optional:

| Setting | What it does |
| --- | --- |
| `REGISTRATION` | `open`, `invite_only` or `closed` |
| `API_WORKERS` | Two per CPU core; 4 on the smallest server |
| `PG_SHARED_BUFFERS`, `PG_EFFECTIVE_CACHE_SIZE` | A quarter and three-eighths of the memory |
| `UNPAYWALL_EMAIL` | Finding open-access PDFs |
| `LLM_*` | AI screening suggestions |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | "Sign in with Google" |
| `ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET` | "Sign in with ORCID", for accounts that link their iD (README) |

Then:

```bash
make prod-up                                                  # build, start, wait until healthy
make prod-create-admin email=you@example.org name="Your Name" # asks for the password
```

`make prod-up` builds the images, brings the database to the latest migration and
starts everything. Caddy gets the certificate the first time someone visits.

ClamAV downloads its signatures on first start, which takes a few minutes. Until then,
PDF uploads wait for their scan.

## Updating

```bash
make prod-update   # git pull, rebuild what changed, migrate, restart
```

Migrations run before the new API starts. To move to a particular release instead,
check out its tag and run `make prod-up`.

## Day to day

- **Health.** The instance admin panel (`/admin/health`) shows the worker, the queue, the
  disk, the database size and the last backup.
- **Logs.** `make prod-logs` follows them. Each service keeps at most five 10 MB files.
- **Stopping.** `make prod-down` stops the stack; the data volumes stay.
- **Backups.** See [Backups](#backups).

## What is exposed, and what is not

- **The firewall** (guide 16.3) allows 80 and 443, TCP and UDP, and SSH with keys only
  (`PasswordAuthentication no`). Everything else is closed.

- **Caddy** redirects HTTP to HTTPS and sends HSTS (preload), a strict Content Security
  Policy and the other headers in `Caddyfile`. It speaks HTTP/2 and HTTP/3.
- **PostgreSQL, Redis, the API, the worker and ClamAV** have no ports on the host.
- **`.env`** holds every secret. Keep it readable by its owner only (`chmod 600`), and
  never commit it.
- **Before launch,** run the OWASP ZAP baseline against the new site. Run it from a
  checkout that can reach it, with the URL as the target (see `make zap`). CI runs it on
  every push.

## Trying the production stack on one machine

This is how the budgets in docs/performance.md were measured. Write a separate env file
with test secrets and these settings:

```
WINNOW_ENV_FILE=/path/to/trial.env
SITE_ADDRESS=localhost
PUBLIC_URL=https://localhost:8443
HTTP_PORT=8088
HTTPS_PORT=8443
```

Then start it with that file, leaving out ClamAV to save memory:

```bash
docker compose -f docker-compose.prod.yml --env-file trial.env \
  up -d --build --wait db redis migrate api worker web caddy
```

Caddy serves `https://localhost:8443` with its own local certificate. The trial uses its
own data volumes (project `winnow-prod`) and never touches the development ones.

## Backups

`make prod-backup` writes one encrypted file, `backups/winnow-<date>T<time>Z.tar.age`,
holding four things:

- the database, as a `pg_dump` in custom format;
- every uploaded file;
- a copy of `.env`, secrets included, so the file is all you need after losing the
  server;
- a manifest.

The file is encrypted with [age](https://age-encryption.org) to a public key, so a
stolen backup is useless without the private key, which never goes on the server.

Rotation keeps the newest backup of each of the last 7 days, 4 weeks and 6 months. The
admin health page shows the last backup.

**Set up once:**

1. **Make the key pair on your own computer**, not on the server. Keep `winnow-backup.key`
   somewhere safe and separate (a password manager): without it, no backup can be read.

   ```bash
   age-keygen -o winnow-backup.key
   ```

2. **Tell the server the public key.** `age-keygen` prints it as `Public key: age1…`. In
   the server's `.env`, set `AGE_RECIPIENT=age1…`, and optionally `BACKUP_DIR` (default
   `backups`). Install age on the server with `sudo apt install age`.

3. **Back up nightly** with cron (`crontab -e` as the user that runs Docker):

   ```
   15 2 * * * cd /srv/winnow && make prod-backup >> backups/backup.log 2>&1
   ```

4. **Copy backups off the server**, since a backup on the same disk dies with it. Every
   file in `backups/` is encrypted, so any storage will do. For example:

   ```bash
   rclone sync /srv/winnow/backups remote:winnow-backups
   ```

**Restoring,** on the same server or a new one set up as above. Copy the backup and the
private key there, then run:

```bash
AGE_IDENTITY=/path/to/winnow-backup.key make prod-restore BACKUP=backups/winnow-….tar.age
```

It stops the API and the worker and replaces the database and the files. Then it starts
them again, running any newer migrations first. It also saves the backed-up env file
beside the backup, so you can compare it with the current one; delete it afterwards.

**The restore itself is tested.** `make restore-test` backs up a small review, destroys
the data, restores it into a fresh database and checks that everything came back. It runs
as a separate Docker project and touches nothing else. CI runs it monthly, and whenever
the backup code or the schema changes (`.github/workflows/restore.yml`).
