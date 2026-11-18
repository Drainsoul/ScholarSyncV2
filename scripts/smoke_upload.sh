#!/bin/sh
# Smoke test for the explore stack: sign in as the demo student, upload a file straight to storage,
# confirm it, then download it through the app and compare the bytes.
# Usage: sh scripts/smoke_upload.sh <app base URL>
set -eu

app="${1:?app base URL}"
password="${SMOKE_STUDENT_PASSWORD:-explore-demo-2026}"
jar="$(mktemp)"
original="$(mktemp)"
downloaded="$(mktemp)"
trap 'rm -f "$jar" "$original" "$downloaded"' EXIT

fail() {
  echo "$1" >&2
  exit 1
}

# json_field <field>: read one field from the JSON on stdin.
json_field() {
  python3 -c 'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

token="$(curl -fsS -c "$jar" -b "$jar" "$app/accounts/login/" \
  | grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' | head -n 1 | sed 's/.*value="//; s/"$//')"
[ -n "$token" ] || fail "no CSRF token on the login form"

code="$(curl -sS -o /dev/null -w "%{http_code}" -c "$jar" -b "$jar" \
  -H "Referer: $app/accounts/login/" \
  --data-urlencode "csrfmiddlewaretoken=$token" \
  --data-urlencode "login=student@scholarsync.test" \
  --data-urlencode "password=$password" \
  "$app/accounts/login/")"
[ "$code" = "302" ] || fail "sign-in was not accepted (HTTP $code)"

# Django rotates the CSRF cookie on login, so read it again from the jar.
csrf="$(awk '$6 == "csrftoken" { print $7 }' "$jar" | tail -n 1)"
[ -n "$csrf" ] || fail "no csrftoken cookie after sign-in"

printf '%%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%%%EOF\n' > "$original"
size="$(wc -c < "$original" | tr -d ' ')"

intent="$(curl -sS -w '\n%{http_code}' -c "$jar" -b "$jar" \
  -H "X-CSRFToken: $csrf" -H "Referer: $app/" -H "Content-Type: application/json" \
  --data "{\"purpose\": \"document\", \"name\": \"smoke.pdf\", \"type\": \"application/pdf\", \"size\": $size}" \
  "$app/files/uploads/")"
code="$(printf '%s' "$intent" | tail -n 1)"
body="$(printf '%s' "$intent" | sed '$d')"
[ "$code" = "201" ] || fail "upload intent was not accepted (HTTP $code): $body"
put_url="$(printf '%s' "$body" | json_field url)"
content_type="$(printf '%s' "$body" | python3 -c 'import json, sys; print(json.load(sys.stdin)["headers"]["Content-Type"])')"
confirm_url="$(printf '%s' "$body" | json_field confirm_url)"

code="$(curl -sS -o /dev/null -w "%{http_code}" -X PUT \
  -H "Content-Type: $content_type" --data-binary "@$original" "$put_url")"
[ "$code" = "200" ] || fail "storage did not accept the upload (HTTP $code)"

confirm="$(curl -sS -w '\n%{http_code}' -c "$jar" -b "$jar" -X POST \
  -H "X-CSRFToken: $csrf" -H "Referer: $app/" "$app$confirm_url")"
code="$(printf '%s' "$confirm" | tail -n 1)"
body="$(printf '%s' "$confirm" | sed '$d')"
[ "$code" = "200" ] || fail "upload was not confirmed (HTTP $code): $body"
download_url="$(printf '%s' "$body" | json_field download_url)"

headers="$(curl -sS -o /dev/null -D - -c "$jar" -b "$jar" "$app$download_url")"
printf '%s' "$headers" | head -n 1 | grep -q ' 302' || fail "download did not redirect: $(printf '%s' "$headers" | head -n 1)"
location="$(printf '%s' "$headers" | tr -d '\r' | sed -n 's/^[Ll]ocation: //p' | head -n 1)"
[ -n "$location" ] || fail "download redirect has no Location"

curl -fsS -o "$downloaded" "$location" || fail "could not fetch the file from storage"
cmp -s "$original" "$downloaded" || fail "downloaded file differs from the original"

echo "upload round trip passed"
