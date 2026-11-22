#!/usr/bin/env sh
set -eu
BASE="${BASE_URL:-https://localhost:8443}"
COOKIE="$(mktemp)"
trap 'rm -f "$COOKIE"' EXIT

login_status=$(curl -skc "$COOKIE" -o /dev/null -w '%{http_code}' -X POST "$BASE/login" -d 'username=student&password=1234')
[ "$login_status" = "302" ] || { echo 'FAULT TEST FAILED: student login did not return 302' >&2; exit 1; }

healthy_courses=$(curl -skb "$COOKIE" "$BASE/courses")
printf '%s' "$healthy_courses" | grep -q 'Open Courses' || { echo 'FAULT TEST FAILED: healthy courses page missing' >&2; exit 1; }

for service in auth-node course-node grade-node audit-node db-replica; do
  docker compose stop "$service" >/dev/null 2>&1
  sleep 2
  case "$service" in
    auth-node)
      status=$(curl -skc /tmp/fault-auth-cookie -o /tmp/fault-auth.html -w '%{http_code}' -X POST "$BASE/login" -d 'username=student&password=1234')
      [ "$status" = "503" ] || { echo 'FAULT TEST FAILED: auth-node did not report unavailable login' >&2; exit 1; };;
    course-node)
      curl -skb "$COOKIE" "$BASE/courses" | grep -q 'Unavailable' || { echo 'FAULT TEST FAILED: course-node degraded page missing' >&2; exit 1; };;
    grade-node)
      curl -skb "$COOKIE" "$BASE/grades" | grep -q 'Unavailable' || { echo 'FAULT TEST FAILED: grade-node degraded page missing' >&2; exit 1; };;
    audit-node)
      curl -skb "$COOKIE" "$BASE/courses" | grep -q 'Open Courses' || { echo 'FAULT TEST FAILED: audit-node affected unrelated courses' >&2; exit 1; };;
    db-replica)
      curl -skb "$COOKIE" "$BASE/courses" | grep -Eq 'Open Courses|Unavailable' || { echo 'FAULT TEST FAILED: replica fallback/courses page missing' >&2; exit 1; };;
  esac
  docker compose start "$service" >/dev/null 2>&1
  echo "PASS: $service isolation"
done
echo 'FAULT TEST PASSED'
