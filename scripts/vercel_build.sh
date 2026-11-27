#!/bin/sh
# Vercel's build step for branch `demo` (docs/hosted-demo.md). `vercel build` runs it inside the
# GitHub Actions deploy job, where uv, Python 3.13 and Node 22 are already set up.
set -eu
(cd frontend && npm ci && npm run build)
uv run --no-dev python manage.py collectstatic --noinput
