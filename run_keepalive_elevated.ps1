# 세션 유지 스크립트를 관리자 권한으로 백그라운드 실행한다.
# CYBOS Plus(CpStart.exe)와 권한 레벨이 같아야 COM 연결이 된다.
#
# 창을 닫으면 종료된다. 계속 돌리려면 창을 열어두거나 작업 스케줄러에 등록한다.
#
# 이 .ps1 은 UTF-8 BOM 으로 저장할 것. 로그 리다이렉트는 cmd 를 쓴다.

$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'C:\Workspace\CybosQuant'

$py = 'C:\Program Files (x86)\Python310-32\python.exe'
$log = 'C:\Workspace\CybosQuant\keepalive.log'

& cmd.exe /c "`"$py`" -u keepalive.py >> `"$log`" 2>&1"
