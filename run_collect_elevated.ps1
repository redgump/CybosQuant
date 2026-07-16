# 전체 종목 수집을 관리자 권한으로 실행하고 출력을 로그 파일로 남긴다.
# CYBOS Plus(CpStart.exe)가 관리자 권한으로 실행되므로, COM 연결을 위해
# 스크립트도 같은 권한 레벨이어야 한다.
#
#   powershell -ExecutionPolicy Bypass -File run_collect_elevated.ps1
#
# 10시간 이상 도는 작업이므로:
#   - python -u : 출력 버퍼링을 끈다. 안 그러면 리다이렉트 시 블록 버퍼링이
#                 걸려 로그가 한참 뒤에야 쌓여 진행 상황을 볼 수 없다.
#   - 로그는 실행 시각으로 파일명을 나눠 재실행해도 이전 로그가 남게 한다.

$env:PYTHONIOENCODING = 'utf-8'
# PowerShell 5.1 은 네이티브 프로세스 stdout 을 콘솔 OEM 코드페이지로 디코딩한다.
# 이걸 UTF-8 로 맞춰야 파이썬이 낸 한글이 리다이렉트 파일에서 깨지지 않는다.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location 'C:\Workspace\CybosQuant'

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = "C:\Workspace\CybosQuant\collect_$stamp.log"

"수집 시작: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -Encoding utf8 $log
& "C:\Program Files (x86)\Python310-32\python.exe" -u collect_minutes.py *>> $log
"EXITCODE=$LASTEXITCODE  종료: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" |
    Out-File -Append -Encoding utf8 $log
