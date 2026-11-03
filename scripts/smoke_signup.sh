#!/bin/sh
# Smoke test for the explore stack: sign up, then wait for the verification email in Mailpit.
# Usage: sh scripts/smoke_signup.sh <app base URL> <Mailpit base URL>
set -eu

app="${1:?app base URL}"
mail="${2:?Mailpit base URL}"
address="smoke@scholarsync.test"
jar="$(mktemp)"
trap 'rm -f "$jar"' EXIT

token="$(curl -fsS -c "$jar" -b "$jar" "$app/accounts/signup/" \
  | grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' | head -n 1 | sed 's/.*value="//; s/"$//')"
if [ -z "$token" ]; then
  echo "no CSRF token on the signup form" >&2
  exit 1
fi

curl -fsS -o /dev/null -c "$jar" -b "$jar" \
  -H "Referer: $app/accounts/signup/" \
  --data-urlencode "csrfmiddlewaretoken=$token" \
  --data-urlencode "email=$address" \
  --data-urlencode "full_name=Smoke Test" \
  --data-urlencode "password1=smoke-signup-2026" \
  --data-urlencode "password2=smoke-signup-2026" \
  --data-urlencode "consent=on" \
  "$app/accounts/signup/"

for _ in $(seq 1 30); do
  total="$(curl -fsS "$mail/api/v1/search?query=to:$address" | grep -o '"total":[0-9]*' | head -n 1 | grep -o '[0-9]*$' || true)"
  if [ "${total:-0}" -ge 1 ]; then
    echo "verification email reached Mailpit"
    exit 0
  fi
  sleep 1
done
echo "no verification email reached Mailpit" >&2
exit 1
