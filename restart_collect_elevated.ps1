# 진행 중인 수집을 정리하고 다시 시작한다 (권한 상승 1회로 처리).
#
# 중간에 종료해도 안전하다: save_csv() 가 임시 파일에 쓰고 os.replace 로
# 교체하므로 반쪽 CSV 가 남지 않고, SKIP_EXISTING=True 라 이미 받은 종목은
# 재시작 시 건너뛴다. 남은 .tmp 파일만 청소한다.
#
# 이 .ps1 은 반드시 UTF-8 BOM 으로 저장할 것 (PowerShell 5.1 파싱 문제).

Set-Location 'C:\Workspace\CybosQuant'

# 1) 기존 수집 프로세스 종료 (32비트 파이썬만 골라서)
$killed = 0
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        if ($_.Path -like '*Python310-32*') {
            Stop-Process -Id $_.Id -Force
            $killed++
        }
    } catch { }
}
Write-Host "종료한 수집 프로세스: $killed 개"

# 2) 중단 시점에 남은 임시 파일 청소
$tmp = @(Get-ChildItem 'C:\Workspace\CybosQuant\data\*.tmp' -ErrorAction SilentlyContinue)
if ($tmp.Count -gt 0) {
    $tmp | Remove-Item -Force
    Write-Host "임시 파일 정리: $($tmp.Count) 개"
}

$done = @(Get-ChildItem 'C:\Workspace\CybosQuant\data\*_1m.csv' -ErrorAction SilentlyContinue)
Write-Host "이미 수집된 종목: $($done.Count) 개 (재시작 시 건너뜀)"

# 3) 고쳐진 래퍼로 수집 재시작
& 'C:\Workspace\CybosQuant\run_collect_elevated.ps1'
