# 매일 분봉 증분 업데이트를 관리자 권한으로 실행한다.
#
# 1) 리허설(probe_update.py): 한 종목의 사본에 실전과 동일한 이어붙이기를
#    수행해 무결성을 확인한다. 실패하면 전체 실행을 하지 않는다.
# 2) 통과하면 전체 종목(collect_minutes.py)을 증분 모드로 실행한다.
#
# 리허설을 같은 창에서 먼저 돌리는 이유는 UAC 승인을 한 번만 받기 위해서다.
#
# 이 .ps1 은 반드시 UTF-8 BOM 으로 저장할 것 (PowerShell 5.1 파싱 문제).
# 로그 리다이렉트는 cmd 를 쓴다 (PS 5.1 의 '>' 는 UTF-16LE 로 재인코딩).

$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'C:\Workspace\CybosQuant'

$py = 'C:\Program Files (x86)\Python310-32\python.exe'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = "C:\Workspace\CybosQuant\update_$stamp.log"

& cmd.exe /c "`"$py`" -u probe_update.py > `"$log`" 2>&1"
$rc = $LASTEXITCODE
Write-Host "리허설 종료코드=$rc"

if ($rc -ne 0) {
    "`n[중단] 리허설 실패로 전체 실행을 건너뜁니다." |
        Out-File -Append -Encoding utf8 $log
    Write-Host "리허설 실패 - 전체 실행 안 함. 로그=$log"
    exit 1
}

& cmd.exe /c "echo. >> `"$log`" && echo ===== 전체 증분 업데이트 시작 ===== >> `"$log`" && `"$py`" -u collect_minutes.py >> `"$log`" 2>&1"
Write-Host "전체 실행 종료코드=$LASTEXITCODE  로그=$log"
