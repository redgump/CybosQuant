# 진단 스크립트를 관리자 권한으로 실행한다 (CYBOS COM 은 권한 일치 필요).
# 이 .ps1 은 UTF-8 BOM 으로 저장할 것. 로그 리다이렉트는 cmd 를 쓴다.

$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'C:\Workspace\CybosQuant'

$py = 'C:\Program Files (x86)\Python310-32\python.exe'
$log = 'C:\Workspace\CybosQuant\diag.log'

& cmd.exe /c "`"$py`" -u probe_diag.py > `"$log`" 2>&1"
Write-Host "종료코드=$LASTEXITCODE  로그=$log"
