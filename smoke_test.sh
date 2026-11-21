#!/usr/bin/env sh
set -eu
BASE="${BASE_URL:-https://localhost:8443}"
STUDENT="$(mktemp)"
FACULTY="$(mktemp)"
trap 'rm -f "$STUDENT" "$FACULTY"' EXIT

status=$(curl -skc "$STUDENT" -o /dev/null -w '%{http_code}' -X POST "$BASE/login" -d 'username=student&password=1234')
[ "$status" = "302" ] || { echo "Student login failed: $status"; exit 1; }
curl -skb "$STUDENT" "$BASE/courses" | grep -q 'Open Courses'
curl -skb "$STUDENT" -X POST "$BASE/courses/3/enroll" | grep -Eq 'Enrolled successfully|Already enrolled'
curl -skb "$STUDENT" "$BASE/grades" | grep -q 'Grades'

status=$(curl -skc "$FACULTY" -o /dev/null -w '%{http_code}' -X POST "$BASE/login" -d 'username=faculty&password=1234')
[ "$status" = "302" ] || { echo "Faculty login failed: $status"; exit 1; }
curl -skb "$FACULTY" -X POST "$BASE/grades/upload" -d 'student_id=11111111-1111-1111-1111-111111111111&course_id=3&grade=A' | grep -q 'Grade saved'

curl -skb "$STUDENT" -c "$STUDENT" -o /dev/null -X POST "$BASE/logout"
echo 'SMOKE TEST PASSED'
