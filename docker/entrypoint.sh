#!/bin/sh
# Prepare the database, then hand over to the container command.
# Started as `sh /app/docker/entrypoint.sh`, so no executable bit is needed (Windows checkouts).
set -eu

# Only the web container prepares the database; the worker sets SKIP_PREPARE=1 so two containers
# never migrate or load the demo at the same time.
if [ "${SKIP_PREPARE:-0}" != "1" ]; then
  # Migrations run as the schema owner when DATABASE_URL_MIGRATIONS is set (the app itself then
  # uses a role that can't change tables), and need a direct connection when DATABASE_URL goes
  # through a pooler.
  DATABASE_URL="${DATABASE_URL_MIGRATIONS:-${DATABASE_URL_UNPOOLED:-$DATABASE_URL}}" python manage.py prepare

  case "${SCHOLARSYNC_EXPLORE:-false}" in
    true | True | TRUE | 1 | yes | on)
      echo "ScholarSync is running: http://localhost:${APP_PORT:-8000}  (test accounts: see README.md; email inbox: http://localhost:${MAIL_PORT:-8025})"
      ;;
  esac
fi

# The app and the worker never see the owner's URL: only prepare needs it, and anything running in
# the app process could otherwise read it from the environment.
unset DATABASE_URL_MIGRATIONS DATABASE_URL_UNPOOLED

exec "$@"
