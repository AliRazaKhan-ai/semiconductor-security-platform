# Troubleshooting Guide

## 1. Diagnostic order

Use this order to avoid changing several systems at once:

1. Check disk space.
2. Check Python environment.
3. Check configuration and secrets.
4. Check backend process.
5. Check readiness.
6. Check event-store integrity.
7. Check model loading.
8. Check hardware integrations.
9. Check blockchain services.
10. Check browser/API behaviour.
11. Run targeted tests before the full suite.

## 2. Backend does not start

Check:

```bash
cd ~/semiconductor_security_platform
source venv/bin/activate
python -m py_compile app/factory.py manage.py
tail -n 200 runtime/backend.log
```

Possible causes:

- port 5000 already in use;
- missing Python dependency;
- invalid configuration;
- unwritable runtime directory;
- unsupported TensorFlow/Python combination;
- stale PID file.

Port check:

```bash
ss -ltnp | grep ':5000'
```

Stop the old process through the project script rather than killing random PIDs:

```bash
./scripts/runtime/stop_backend.sh
./scripts/runtime/start_backend.sh
```

## 3. Readiness is not `ready`

```bash
curl -sS http://localhost:5000/health/ready \
  | python -m json.tool
```

Inspect the failing check. Ensure directories exist and are writable:

```bash
mkdir -p data/event_store data/indexes data/snapshots data/audit runtime/locks
find data runtime -maxdepth 2 -type d -printf '%M %u:%g %p\n'
```

## 4. `ModuleNotFoundError`

Confirm the active interpreter:

```bash
which python
python --version
python -m pip --version
```

Expected path should include the project `venv`.

Reinstall:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

## 5. TensorFlow import error

The requirements restrict TensorFlow to supported Python versions. Use Python 3.12 for the complete stack.

```bash
python --version
python -m pip show tensorflow
```

If Python is 3.14, create a Python 3.12 environment.

## 6. Model file missing or integrity failure

```bash
find models -type f -printf '%p %s bytes\n' | sort
python -m pytest tests/ai -q
```

Do not create fake empty model files. Restore the trained artefact and matching manifest. If the fallback engine is active, the final policy should clearly state degraded AI availability.

## 7. Event-store integrity error

Use the registered Flask CLI:

```bash
flask --app 'app.factory:create_app' verify-event-store
```

Back up data before recovery:

```bash
tar -czf event-store-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  data/event_store data/indexes data/snapshots data/audit
```

Then use the project's rebuild command:

```bash
flask --app 'app.factory:create_app' rebuild-event-store
```

Never delete the immutable event directory merely to clear an error.

## 8. Dashboard says no backend events

Check API data first:

```bash
curl -fsS http://localhost:5000/api/v1/scans/latest \
  | python -m json.tool
```

Check JavaScript syntax:

```bash
node --check app/dashboard/static/js/dashboard.js
```

Run dashboard contracts:

```bash
python -m pytest tests/dashboard tests/static -q
```

Hard refresh:

```text
Ctrl + Shift + R
```

The dashboard uses REST-derived notification fallback because terminal scans can run in a process separate from Flask. Socket.IO is supplementary for same-process events.

## 9. Socket.IO connected but events are missing

Confirm the client namespace is `/events` and listens for `platform.event`.

A namespace-wide emit must omit `to`; using `to="all"` requires a room named `all` and can silently miss clients.

Do not use multiple Gunicorn workers unless Socket.IO has a shared message queue.

## 10. Test fails because a comment contains code text

A source-text contract can match comments as well as executable code. Prefer syntax-aware or narrowly scoped assertions. If a test intentionally checks raw text, remove misleading literals from comments.

Example previously observed:

```text
assert 'to="all"' not in source
```

A comment containing that phrase failed the test even though the runtime code was correct.

## 11. Fabric endorsement or private-data failure

Check:

- network containers;
- channel name;
- chaincode name and sequence;
- organisation MSP identity;
- collection configuration;
- peer endorsement policy;
- commit status.

Use project status scripts and inspect container logs:

```bash
docker ps
docker logs <peer-container> --tail 200
```

A private collection requires participating organisations and peers to satisfy its policy.

## 12. Ethereum or Anvil unavailable

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
  http://localhost:8545
```

For Docker-to-host access use:

```text
http://host.docker.internal:8545
```

Check the configured contract address and persisted Anvil state. Restarting an ephemeral chain without state can invalidate the previous deployment address.

## 13. Docker container is unhealthy

```bash
docker compose ps
docker compose logs --tail=200 semisecure
docker inspect semisecure-platform \
  --format '{{json .State.Health}}' | python -m json.tool
```

Check mounted directory ownership. The production image uses a non-root user, so host directories must be writable as configured.

## 14. Disk is full

```bash
df -h
du -xh --max-depth=1 . | sort -h
docker system df
```

Safe candidates may include:

- old runtime logs;
- temporary ZIP files;
- Python caches;
- unused Docker build cache;
- old Anvil temporary state;
- superseded backups after verification.

Do not delete active event, audit, model, Fabric, or Ethereum state without a backup.

## 15. Git push says `origin` is not a repository

```bash
git remote -v
```

Add the correct remote:

```bash
git remote add origin \
  https://github.com/AliRazaKhan-ai/semiconductor-security-platform.git
```

Then push the intended branch:

```bash
git push -u origin phase-4-production-hardening
```

A force push replaces remote branch history. Use it only after verifying the repository URL, branch, and local commit.

## 16. Secret files appear in Git status

```bash
git status --short
git check-ignore -v .env.production
```

Add secret/runtime patterns to `.gitignore`. If a secret was already committed, removing the current file is insufficient; rotate the secret and clean repository history.

## 17. Pipeline gives the wrong final routing

Run the regression test:

```bash
python -m pytest \
  tests/pipeline/test_permanent_rejection_routing.py \
  -q
```

Inspect the orchestrator's decision hierarchy. Permanent rejection conditions must be evaluated before generic quarantine or manual-review routing.

## 18. Useful evidence to collect before asking for help

```bash
{
  echo '=== status ==='
  git status --short
  echo '=== python ==='
  python --version
  echo '=== disk ==='
  df -h
  echo '=== readiness ==='
  curl -sS http://localhost:5000/health/ready
  echo
  echo '=== backend log ==='
  tail -n 100 runtime/backend.log
} > diagnostic_report.txt
```

Remove secrets before sharing the report.
