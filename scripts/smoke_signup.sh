#!/bin/sh
# Smoke test for the explore stack: sign up, then wait for the verification email in Mailpit.
# Usage: sh scripts/smoke_signup.sh <app base URL> <Mailpit base URL>
set -eu

app="${1:?app base URL}"
mail="${2:?Mailpit base URL}"
# A fresh address per run, so a persistent stack that already holds an earlier run still works.
address="smoke+$(date +%s)@scholarsync.test"
query_address="smoke%2B${address#smoke+}"
password="${SMOKE_PASSWORD:-smoke-signup-2026}"
jar="$(mktemp)"
trap 'rm -f "$jar"' EXIT

token="$(curl -fsS -c "$jar" -b "$jar" "$app/accounts/signup/" \
  | grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' | head -n 1 | sed 's/.*value="//; s/"$//')"
if [ -z "$token" ]; then
  echo "no CSRF token on the signup form" >&2
  exit 1
fi

code="$(curl -sS -o /dev/null -w "%{http_code}" -c "$jar" -b "$jar" \
  -H "Referer: $app/accounts/signup/" \
  --data-urlencode "csrfmiddlewaretoken=$token" \
  --data-urlencode "email=$address" \
  --data-urlencode "full_name=Smoke Test" \
  --data-urlencode "password1=$password" \
  --data-urlencode "password2=$password" \
  --data-urlencode "consent=on" \
  "$app/accounts/signup/")"
if [ "$code" != "302" ]; then
  echo "signup was not accepted (HTTP $code)" >&2
  exit 1
fi

for _ in $(seq 1 30); do
  found="$(curl -fsS "$mail/api/v1/search?query=to:$query_address" | grep -o '"messages_count":[0-9]*' | head -n 1 | grep -o '[0-9]*$' || true)"
  if [ "${found:-0}" -ge 1 ]; then
    echo "verification email reached Mailpit"
    exit 0
  fi
  sleep 1
done
echo "no verification email reached Mailpit" >&2
exit 1
