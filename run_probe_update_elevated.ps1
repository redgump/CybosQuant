# 증분 리허설만 단독으로 관리자 권한 실행한다 (전체 수집은 하지 않는다).
# 경로 변경 등 설정을 바꾼 뒤 실전 경로가 살아 있는지 빠르게 확인할 때 쓴다.
#
# 이 .ps1 은 UTF-8 BOM 으로 저장할 것. 로그 리다이렉트는 cmd 를 쓴다.

$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'C:\Workspace\CybosQuant'

$py = 'C:\Program Files (x86)\Python310-32\python.exe'
$log = 'C:\Workspace\CybosQuant\probe_update.log'

& cmd.exe /c "`"$py`" -u probe_update.py > `"$log`" 2>&1"
Write-Host "종료코드=$LASTEXITCODE  로그=$log"
