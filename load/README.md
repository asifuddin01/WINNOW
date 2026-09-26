# Load test

Guide section 13: 50 reviewers screening at once, each deciding every 3 seconds, for 10
minutes. The budget is p95 < 100 ms with errors under 0.1%.

```bash
make load                                  # 50 reviewers, 10 minutes
make load reviewers=5 duration=45s         # a quick check that the harness works
```

`make load` runs three steps:

1. `backend/benchmarks/load_setup.py make` creates throwaway accounts
   (`e2e-load-…@example.com`) and a review of 20,000 generated records that they all
   screen. It signs each account in and writes the sessions to
   `backend/benchmarks/data/load.json` (git-ignored).
2. `load/decide.js` runs in the `k6` compose service (profile `load`), through Caddy.
   Each reviewer asks for the next ten records and decides the first, once every three
   seconds on average, independently of the others.
3. `load_setup.py clear` deletes the review and the sessions file, whatever k6 reported.

k6 exits with an error when a threshold fails, and `make load` passes that exit code on.

**Run it against the production stack.** The development API is a single Uvicorn
process with `--reload`, so a burst of requests queues behind itself. The guide's
setting is two workers per core. docs/performance.md has the results.

For a production trial on one machine (docs/deploy.md), prepare the review with the trial's
API image (its setup refuses a production instance, so it runs as development against the
trial's database), then run k6 on the trial's network. Caddy answers only to
SITE_ADDRESS, so point that name at Caddy's address:

```bash
docker compose -f docker-compose.prod.yml --env-file trial.env run --rm --no-deps \
  -e WINNOW_ENV=development -v "$PWD/backend:/app" api python -m benchmarks.load_setup make
docker run --rm --network winnow-prod_default -v "$PWD/load:/scripts:ro" \
  -v "$PWD/backend/benchmarks/data:/load:ro" -e BASE_URL=https://localhost \
  -e TARGET_IP=$(docker inspect winnow-prod-caddy-1 -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}') \
  -e INSECURE_TLS=1 grafana/k6:2.3.0 run /scripts/decide.js
docker compose -f docker-compose.prod.yml --env-file trial.env run --rm --no-deps \
  -e WINNOW_ENV=development -v "$PWD/backend:/app" api python -m benchmarks.load_setup clear
```

**If the image pull hangs** on `docker-credential-desktop get` (the macOS Keychain helper
waits forever), pull the public image without it:

```bash
DOCKER_CONFIG=$(mktemp -d) docker pull grafana/k6:2.3.0
```
