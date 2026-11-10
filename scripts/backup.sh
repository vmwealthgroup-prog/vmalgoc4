#!/bin/sh
# Dumps the Postgres database from the compose stack to backups/vmalgo-YYYYmmdd-HHMM.sql.gz (keeps the newest 14).
# Restore:  gunzip -c backups/FILE.sql.gz | docker compose exec -T db psql -U vmalgo -d vmalgo
# Also back up .env: without ENCRYPTION_KEY the saved broker keys cannot be decrypted.
set -eu
cd "$(dirname "$0")/.."; mkdir -p backups
f="backups/vmalgo-$(date +%Y%m%d-%H%M).sql.gz"
docker compose exec -T db pg_dump -U vmalgo -d vmalgo | gzip > "$f"
echo "wrote $f ($(du -h "$f" | cut -f1))"
ls -1t backups/vmalgo-*.sql.gz | tail -n +15 | xargs -r rm --
