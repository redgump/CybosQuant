# 전체 종목 수집을 관리자 권한으로 실행하고 출력을 로그 파일로 남긴다.
# CYBOS Plus(CpStart.exe)가 관리자 권한으로 실행되므로, COM 연결을 위해
# 스크립트도 같은 권한 레벨이어야 한다.
#
#   powershell -ExecutionPolicy Bypass -File run_collect_elevated.ps1
#
# 10시간 이상 도는 작업이라 로그가 유일한 감시 수단이다. 그래서:
#
#   - python -u : 출력 버퍼링을 끈다. 안 그러면 리다이렉트 시 블록 버퍼링이
#                 걸려 로그가 한참 뒤에야 쌓여 진행 상황을 볼 수 없다.
#   - cmd /c 리다이렉트 : PowerShell 5.1 의 '*>>' 는 출력을 UTF-16LE 로
#                 다시 인코딩해서 쓴다. 파이썬이 UTF-8 로 낸 바이트와 섞이면
#                 어떤 인코딩으로 열어도 한쪽이 깨진다. cmd 의 리다이렉트는
#                 바이트를 그대로 통과시키므로 로그가 순수 UTF-8 로 남는다.
#   - 이 .ps1 은 반드시 UTF-8 BOM 으로 저장할 것. PowerShell 5.1 은 BOM 이
#                 없으면 .ps1 을 CP949 로 파싱해서 한글이 깨진다.

$env:PYTHONIOENCODING = 'utf-8'

Set-Location 'C:\Workspace\CybosQuant'

$py = 'C:\Program Files (x86)\Python310-32\python.exe'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = "C:\Workspace\CybosQuant\collect_$stamp.log"

& cmd.exe /c "`"$py`" -u collect_minutes.py > `"$log`" 2>&1"

Write-Host "종료코드=$LASTEXITCODE  로그=$log"
