$ErrorActionPreference = 'Stop'
$Base = if ($env:BASE_URL) { $env:BASE_URL } else { 'https://localhost:8443' }
$Student = Join-Path $env:TEMP "p4-student-$PID.txt"
$Faculty = Join-Path $env:TEMP "p4-faculty-$PID.txt"
try {
    $login = Invoke-WebRequest -SkipCertificateCheck -SessionVariable studentSession -Method Post -Uri "$Base/login" -Body @{username='student';password='1234'} -MaximumRedirection 0 -ErrorAction SilentlyContinue
    if ($null -eq $studentSession) { throw 'Student login failed' }
    Invoke-WebRequest -SkipCertificateCheck -WebSession $studentSession -Uri "$Base/courses" | Out-Null
    Invoke-WebRequest -SkipCertificateCheck -WebSession $studentSession -Method Post -Uri "$Base/courses/enroll" -Body @{course_id='3'} | Out-Null
    Invoke-WebRequest -SkipCertificateCheck -WebSession $studentSession -Uri "$Base/grades" | Out-Null

    Invoke-WebRequest -SkipCertificateCheck -SessionVariable facultySession -Method Post -Uri "$Base/login" -Body @{username='faculty';password='1234'} -MaximumRedirection 0 -ErrorAction SilentlyContinue | Out-Null
    $upload = Invoke-WebRequest -SkipCertificateCheck -WebSession $facultySession -Method Post -Uri "$Base/grades/upload" -Body @{student_id='11111111-1111-1111-1111-111111111111';course_id='3';grade='A'} -MaximumRedirection 0 -ErrorAction SilentlyContinue
    if ($upload.StatusCode -ne 303) { throw "Grade upload returned HTTP $($upload.StatusCode), expected 303" }
    $gradesPage = Invoke-WebRequest -SkipCertificateCheck -WebSession $facultySession -Uri "$Base/grades"
    if ($gradesPage.Content -notmatch 'Grade saved') { throw 'Faculty grade upload did not report success' }
    Write-Host 'SMOKE TEST PASSED' -ForegroundColor Green
} catch {
    Write-Error "SMOKE TEST FAILED: $($_.Exception.Message)"
    exit 1
}
