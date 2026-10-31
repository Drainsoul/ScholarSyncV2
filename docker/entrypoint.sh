#!/bin/sh
# Prepare the database, then hand over to the container command.
# Started as `sh /app/docker/entrypoint.sh`, so no executable bit is needed (Windows checkouts).
set -eu

# Migrations may need a direct connection when DATABASE_URL goes through a pooler.
DATABASE_URL="${DATABASE_URL_UNPOOLED:-$DATABASE_URL}" python manage.py prepare

case "${SCHOLARSYNC_EXPLORE:-false}" in
  true | True | TRUE | 1 | yes | on)
    echo "ScholarSync is running: http://localhost:${APP_PORT:-8000}  (test accounts: see README.md; email inbox: http://localhost:${MAIL_PORT:-8025})"
    ;;
esac

exec "$@"
