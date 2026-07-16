# 프로브를 관리자 권한으로 실행하고 출력을 파일로 남긴다.
# CYBOS Plus(CpStart.exe)가 관리자 권한으로 실행되므로, COM 연결을 위해
# 스크립트도 같은 권한 레벨이어야 한다.
$env:PYTHONIOENCODING = 'utf-8'
# PowerShell 5.1 은 네이티브 프로세스 stdout 을 콘솔 OEM 코드페이지로 디코딩한다.
# 이걸 UTF-8 로 맞춰야 파이썬이 낸 한글이 리다이렉트 파일에서 깨지지 않는다.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location 'C:\Workspace\CybosQuant'
& "C:\Program Files (x86)\Python310-32\python.exe" probe_minutes.py *> 'C:\Workspace\CybosQuant\probe_out.txt'
"EXITCODE=$LASTEXITCODE" | Out-File -Append -Encoding utf8 'C:\Workspace\CybosQuant\probe_out.txt'
