# 매일 분봉 수집 + 세션 유지를 Windows 작업 스케줄러에 등록한다.
# 관리자 권한으로 실행할 것.
#
#   powershell -ExecutionPolicy Bypass -File register_tasks.ps1
#
# ── 반드시 'Interactive' 로그온 타입이어야 하는 이유 ──────────────────
# CYBOS Plus 는 32비트 COM 서버이고, 실행 중인 CpStart.exe 와 같은 세션에
# 있어야 연결된다. 작업 스케줄러의 "사용자의 로그온 여부에 관계없이 실행"
# (S4U/Password)은 작업을 세션 0 에서 돌리므로, 데스크톱 세션에 떠 있는
# CYBOS 와 통신하지 못해 IsConnect 가 0 이 된다.
# -LogonType Interactive = "사용자가 로그온할 때만 실행" 이라야 한다.
# 즉 이 PC 에 로그온한 상태를 유지해야 자동 수집이 돈다.
#
# -RunLevel Highest = "가장 높은 권한으로 실행" (CpStart.exe 와 권한 일치)
#
# 이 .ps1 은 UTF-8 BOM 으로 저장할 것.

$ErrorActionPreference = 'Stop'

$root = 'C:\Workspace\CybosQuant'
$psExe = 'powershell.exe'
$user  = "$env:USERDOMAIN\$env:USERNAME"

# 로그온한 대화형 세션에서, 관리자 권한으로 실행
$principal = New-ScheduledTaskPrincipal -UserId $user `
    -LogonType Interactive -RunLevel Highest

# 공통 설정
#  StartWhenAvailable : PC 가 꺼져 있어 놓친 실행을 켜진 뒤 따라잡는다
#  AllowStartIfOnBatteries / DontStopIfGoingOnBatteries : 노트북 배터리에서도 실행
#  ExecutionTimeLimit : 수집은 17분이면 끝난다. 3시간이면 넉넉하다.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -MultipleInstances IgnoreNew

# ── 1. 매일 18:00 증분 수집 ───────────────────────────────────────────
# 18:00 인 이유: 정규장은 15:30 에 끝나지만 시간외 단일가가 16:30 까지
# 이어진다. 그 전에 돌리면 시간외 구간이 빠진다.
$t1 = New-ScheduledTaskTrigger -Daily -At '18:00'
$a1 = New-ScheduledTaskAction -Execute $psExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\run_daily_update.ps1`"" `
    -WorkingDirectory $root

Register-ScheduledTask -TaskName 'CybosQuant-DailyUpdate' `
    -Description '매일 18:00 전 종목 1분봉 증분 수집 (CYBOS Plus 로그인 필요)' `
    -Trigger $t1 -Action $a1 -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "[등록] CybosQuant-DailyUpdate  - 매일 18:00"

# ── 2. 세션 유지 (로그온 시 시작) ─────────────────────────────────────
# CYBOS 는 무활동 시 접속을 끊는다. 5분마다 시세 1건을 조회해 살려둔다.
# 재부팅/재로그온 후에도 자동으로 다시 뜬다.
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $user
$a2 = New-ScheduledTaskAction -Execute $psExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\run_keepalive_elevated.ps1`"" `
    -WorkingDirectory $root

# 세션 유지는 계속 돌아야 하므로 시간 제한을 두지 않는다.
$settings2 = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$settings2.ExecutionTimeLimit = 'PT0S'   # 무제한

Register-ScheduledTask -TaskName 'CybosQuant-KeepAlive' `
    -Description 'CYBOS 세션 유지 (5분마다 시세 1건 조회)' `
    -Trigger $t2 -Action $a2 -Principal $principal -Settings $settings2 -Force | Out-Null
Write-Host "[등록] CybosQuant-KeepAlive   - 로그온 시 시작"

Write-Host ""
Write-Host "=== 등록된 작업 ==="
Get-ScheduledTask -TaskName 'CybosQuant-*' |
    Select-Object TaskName, State,
        @{N='LogonType';E={$_.Principal.LogonType}},
        @{N='RunLevel';E={$_.Principal.RunLevel}} |
    Format-Table -AutoSize

Write-Host "다음 실행 예정:"
Get-ScheduledTask -TaskName 'CybosQuant-*' | Get-ScheduledTaskInfo |
    Select-Object TaskName, NextRunTime, LastRunTime, LastTaskResult |
    Format-Table -AutoSize
