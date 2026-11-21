$ErrorActionPreference = 'Stop'
$Base = if ($env:BASE_URL) { $env:BASE_URL } else { 'https://localhost:8443' }
try {
    $login = Invoke-WebRequest -SkipCertificateCheck -SessionVariable studentSession -Method Post -Uri "$Base/login" -Body @{username='student';password='1234'} -MaximumRedirection 0 -ErrorAction SilentlyContinue
    if ($login.StatusCode -ne 302) { throw 'Student login did not return 302' }
} catch {
    Write-Error 'FAULT TEST FAILED: could not log in'; exit 1
}
foreach ($Service in 'auth-node','course-node','grade-node','audit-node','db-replica') {
    docker compose stop $Service | Out-Null
    Start-Sleep -Seconds 2
    try {
        switch ($Service) {
            'auth-node' {
                $result = Invoke-WebRequest -SkipCertificateCheck -Method Post -Uri "$Base/login" -Body @{username='student';password='1234'} -MaximumRedirection 0 -ErrorAction SilentlyContinue
                if ($result.StatusCode -ne 503) { throw 'auth-node login did not show unavailable' }
            }
            'course-node' {
                $result = Invoke-WebRequest -SkipCertificateCheck -WebSession $studentSession -Uri "$Base/courses"
                if ($result.Content -notmatch 'Unavailable') { throw 'course-node degraded page missing' }
            }
            'grade-node' {
                $result = Invoke-WebRequest -SkipCertificateCheck -WebSession $studentSession -Uri "$Base/grades"
                if ($result.Content -notmatch 'Unavailable') { throw 'grade-node degraded page missing' }
            }
            'audit-node' {
                $result = Invoke-WebRequest -SkipCertificateCheck -WebSession $studentSession -Uri "$Base/courses"
                if ($result.Content -notmatch 'Open Courses') { throw 'audit-node affected courses page' }
            }
            'db-replica' {
                $result = Invoke-WebRequest -SkipCertificateCheck -WebSession $studentSession -Uri "$Base/courses"
                if ($result.Content -notmatch 'Open Courses|Unavailable') { throw 'replica fallback/courses page missing' }
            }
        }
    } catch {
        Write-Error "FAULT TEST FAILED: $($_.Exception.Message)"; exit 1
    }
    docker compose start $Service | Out-Null
    Write-Host "PASS: $Service isolation" -ForegroundColor Green
}
Write-Host 'FAULT TEST PASSED' -ForegroundColor Green
