#!/usr/bin/env sh
set -eu
BASE="${BASE_URL:-https://localhost:8443}"
STUDENT="$(mktemp)"
FACULTY="$(mktemp)"
trap 'rm -f "$STUDENT" "$FACULTY"' EXIT

fail() { echo "SMOKE TEST FAILED: $1" >&2; exit 1; }
status=$(curl -skc "$STUDENT" -o /dev/null -w '%{http_code}' -X POST "$BASE/login" -d 'username=student&password=1234') || fail "student login request"
[ "$status" = "302" ] || fail "student login HTTP $status"
curl -skb "$STUDENT" "$BASE/courses" | grep -q 'Open Courses' || fail "course page"
status=$(curl -skb "$STUDENT" -o /dev/null -w '%{http_code}' -X POST "$BASE/courses/enroll" -d 'course_id=3')
[ "$status" = "303" ] || fail "enrollment POST HTTP $status"
curl -skb "$STUDENT" "$BASE/courses" | grep -q 'Open Courses' || fail "course redirect page"
curl -skb "$STUDENT" "$BASE/grades" | grep -q 'Grades' || fail "student grades page"

status=$(curl -skc "$FACULTY" -o /dev/null -w '%{http_code}' -X POST "$BASE/login" -d 'username=faculty&password=1234') || fail "faculty login request"
[ "$status" = "302" ] || fail "faculty login HTTP $status"
status=$(curl -skb "$FACULTY" -c "$FACULTY" -o /dev/null -w '%{http_code}' -X POST "$BASE/grades/upload" -d 'student_id=11111111-1111-1111-1111-111111111111&course_id=3&grade=A')
[ "$status" = "303" ] || fail "grade upload POST HTTP $status"
page=$(curl -skb "$FACULTY" -c "$FACULTY" "$BASE/grades")
printf '%s' "$page" | grep -q 'Grade saved' || fail "faculty grade upload did not report success"
printf '%s' "$page" | grep -q 'Grades' || fail "faculty grade redirect page"

status=$(curl -skb "$STUDENT" -o /dev/null -w '%{http_code}' -X POST "$BASE/logout")
[ "$status" = "302" ] || fail "logout HTTP $status"
echo 'SMOKE TEST PASSED'
