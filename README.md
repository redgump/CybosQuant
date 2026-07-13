# CybosQuant — CYBOS Plus 분봉 수집기

대신증권 **CYBOS Plus** COM API 를 이용해 전체 종목의 분봉을 조회하고
종목별 CSV 파일로 저장한다.

## 새 PC 빠른 설치 (요약)

```powershell
# 1) 소스 받기
git clone https://github.com/redgump/CybosQuant.git
cd CybosQuant

# 2) 32비트 Python 설치 (python.org "Windows installer 32-bit") 후 pywin32 설치
#    아래 py32 = 그 32비트 python.exe 전체 경로
py32 -m pip install -r requirements.txt

# 3) COM 동작 확인 ("COM OK" 나오면 성공)
py32 -c "import win32com.client as w; w.Dispatch('Scripting.Dictionary'); print('COM OK')"

# 4) CYBOS Plus 실행 + 로그인 후, 관리자 권한 PowerShell 에서 실행
py32 collect_minutes.py
```

자세한 단계는 아래 섹션 참고. 각 항목의 배경은 **⚠️ 실행 전 필수 조건**을 먼저 읽을 것.

## ⚠️ 실행 전 필수 조건

CYBOS Plus 는 **32비트 COM API** 다. 따라서 아래 조건을 모두 만족해야 한다.

1. **32비트 Python** (64비트 Python 에서는 CYBOS COM 을 로드할 수 없다.
   설치 경로는 PC 마다 다르다 → 아래 1번 참고. 이 문서에서는 그 실행 파일을
   `py32` 로 표기한다.)
2. `pywin32` 설치 (아래 2번 참고, postinstall 실행 불필요)
3. **CYBOS Plus 실행 후 로그인**된 상태
4. **CYBOS Plus 와 Python 스크립트의 권한(UAC) 레벨이 일치**해야 한다.
   Windows 는 권한이 다른 프로세스 간 COM 연결을 막는다.
   CYBOS Plus(`CpStart.exe`)는 보통 매니페스트상 **관리자 권한으로 실행**되므로,
   **스크립트도 관리자 권한 PowerShell 에서 실행**해야 한다.
   (관리자 PowerShell → `py32 collect_minutes.py`)

---

## 1. 32비트 Python 설치

1. https://www.python.org/downloads/windows/ 접속
2. 원하는 3.x 버전의 **"Windows installer (32-bit)"** 다운로드
   (예: `python-3.12.x-amd32`... 실제 파일명은 `...win32.exe`)
3. 설치 시 **"Add python.exe to PATH"** 체크는 선택.
   64비트와 충돌을 피하려면 별도 경로에 설치하는 것을 권장.
   예: `C:\Python\python312-32`

설치 후 32비트인지 확인:

```powershell
& "C:\Python\python312-32\python.exe" -c "import struct; print(struct.calcsize('P')*8)"
# 32 가 출력되어야 함
```

> 이후 문서에서 이 32비트 실행 파일을 `py32` 로 표기한다.
> 편의를 위해 PowerShell 에서 별칭을 만들어 두면 좋다:
> ```powershell
> Set-Alias py32 "C:\Python\python312-32\python.exe"   # 실제 설치 경로로 교체
> ```

## 2. pywin32 설치 및 동작 확인

```powershell
py32 -m pip install --upgrade pip
py32 -m pip install -r requirements.txt
```

> **`pywin32_postinstall.py` 는 실행하지 않아도 된다.**
> 최근 pywin32 는 pip 휠로 설치하면 필요한 DLL 을 `pywin32_system32`
> 폴더에 넣고 자동으로 DLL 검색 경로에 등록한다. 그래서 이 스크립트는
> 최신 버전 휠에 아예 포함되지 않는다.

설치 후, COM 클라이언트가 실제로 뜨는지 아래로 확인한다 (`OK` 가 나오면 준비 완료):

```powershell
py32 -c "import win32com.client as w; d=w.Dispatch('Scripting.Dictionary'); print('COM OK')"
```

## 3. CYBOS Plus 준비

1. CYBOS Plus 를 **관리자 권한**으로 실행
2. 로그인 (공동인증서/ID)
3. 로그인 상태를 유지한 채로 스크립트를 실행한다.

---

## 사용법

`config.py` 에서 수집 조건을 설정한 뒤 실행한다.

```powershell
# 관리자 권한 PowerShell 에서
py32 collect_minutes.py
```

### 주요 설정 (`config.py`)

| 항목 | 설명 |
|------|------|
| `CHART_PERIOD_MIN` | 분봉 주기 (1, 3, 5분 ...) |
| `REQUEST_TYPE` | `"count"`(최근 N개) 또는 `"period"`(기간) |
| `COUNT` | count 방식일 때 종목당 최대 봉 개수 |
| `START_DATE`/`END_DATE` | period 방식 기간 (YYYYMMDD) |
| `MARKETS` | `[1, 2]` = 코스피+코스닥 |
| `COMMON_STOCK_ONLY` | 보통주만 (ETF/스팩 제외) |
| `LIMIT_STOCKS` | 테스트용, 앞 N개만 (`0`=전체) |
| `SKIP_EXISTING` | 이미 저장된 종목 건너뛰기 (재개용) |

### 저장 결과

종목별로 `data/{종목코드}_{주기}m.csv` 로 저장된다.

```
date,time,open,high,low,close,volume
20250711,900,71000,71200,70900,71100,15230
20250711,901,71100,71300,71100,71250,8420
...
```

- `date` = YYYYMMDD, `time` = HHMM
- 데이터는 시간 오름차순으로 저장

## 중단 / 재개

- 실행 중 `Ctrl+C` 로 중단해도 이미 저장된 CSV 는 유지된다.
- `SKIP_EXISTING = True` 상태로 다시 실행하면 **저장 안 된 종목부터 이어서** 진행한다.

## 요청 제한

CYBOS 는 시세요청이 **15초당 60건**으로 제한된다. 스크립트는 잔여 요청
건수를 확인해 제한에 걸리기 전에 자동으로 대기하므로, 전체 종목 수집은
시간이 오래 걸릴 수 있다(수천 종목 × 연속조회).

## 자주 겪는 문제

| 증상 | 원인 / 해결 |
|------|------|
| `No module named 'win32com'` | 64비트 Python 으로 실행 중이거나 pywin32 미설치. 32비트 `py32` 로 실행 |
| `CYBOS Plus 에 연결되어 있지 않습니다` | CYBOS Plus 미실행/미로그인. 관리자 권한으로 실행 후 로그인 |
| COM 객체 생성 실패 | 관리자 권한 터미널에서 실행. `py32 -m pip install --force-reinstall pywin32` 로 재설치 |
