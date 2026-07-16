# -*- coding: utf-8 -*-
"""단일 종목 1분봉 수집 프로브.

전체 종목 수집 설계를 확정하기 전에, 한 종목으로 아래를 실측한다.

  1. 요청 1회(BlockRequest)당 실제 수신 개수
  2. 연속조회(chart.Continue) 가 실제로 동작하는지
     (비공식 문서상 StockChart 는 연속여부 'X' 로 표기돼 있음)
  3. 1분봉이 실제로 어디서 잘리는지 (공식 Q&A 기준 2년)
  4. 종목당 봉 개수 / CSV 파일 크기 -> 전체 종목 추정치의 근거

32비트 Python + 실행/로그인된 CYBOS Plus + 관리자 권한에서 실행할 것.

    py32 probe_minutes.py
"""

import csv
import os
import sys
import time
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from cybos_client import CybosClient, CybosError

CODE = "A005930"          # 삼성전자
PERIOD_MIN = 1
OUT_DIR = "data"
OUT_FILE = os.path.join(OUT_DIR, "probe_A005930_1m.csv")

# 페이지 폭주 방지. 2년치(약 19만봉)를 요청당 ~2000건으로 받으면 ~95회면 끝난다.
MAX_PAGES = 400

FIELDS = [0, 1, 2, 3, 4, 5, 8]  # 날짜, 시간, 시가, 고가, 저가, 종가, 거래량


def set_inputs_count(chart, code, count):
    chart.SetInputValue(0, code)
    chart.SetInputValue(1, ord("2"))       # 요청구분: 개수
    chart.SetInputValue(4, count)          # 요청개수
    chart.SetInputValue(5, FIELDS)
    chart.SetInputValue(6, ord("m"))       # 분봉
    chart.SetInputValue(7, PERIOD_MIN)
    chart.SetInputValue(9, ord("1"))       # 수정주가


def set_inputs_period(chart, code, start_date, end_date):
    chart.SetInputValue(0, code)
    chart.SetInputValue(1, ord("1"))       # 요청구분: 기간
    chart.SetInputValue(2, int(end_date))  # 종료일
    chart.SetInputValue(3, int(start_date))# 시작일
    chart.SetInputValue(5, FIELDS)
    chart.SetInputValue(6, ord("m"))
    chart.SetInputValue(7, PERIOD_MIN)
    chart.SetInputValue(9, ord("1"))


def read_page(chart):
    """현재 수신 버퍼를 읽어 행 리스트로 반환."""
    received = chart.GetHeaderValue(3)
    rows = []
    for i in range(received):
        rows.append((
            chart.GetDataValue(0, i),  # 날짜 YYYYMMDD
            chart.GetDataValue(1, i),  # 시간 HHMM
            chart.GetDataValue(2, i),  # 시가
            chart.GetDataValue(3, i),  # 고가
            chart.GetDataValue(4, i),  # 저가
            chart.GetDataValue(5, i),  # 종가
            chart.GetDataValue(6, i),  # 거래량
        ))
    return rows


def check_status(chart, label):
    status = chart.GetDibStatus()
    if status != 0:
        raise CybosError(f"{label} 실패 (status={status}): {chart.GetDibMsg1()}")


def fmt_span(rows):
    if not rows:
        return "-"
    lo = min(r[0] for r in rows)
    hi = max(r[0] for r in rows)
    return f"{lo} ~ {hi}"


# --------------------------------------------------------------------------
# TEST 1 + 2: 요청개수 방식 + 연속조회 페이징
# --------------------------------------------------------------------------
def probe_count_paging(client):
    print("\n" + "=" * 72)
    print("[TEST 1/2] 요청개수 방식 + 연속조회(Continue) 페이징")
    print("=" * 72)

    chart = client.chart
    seen = set()
    rows = []
    page_sizes = []
    started = time.time()

    client.wait_for_request_slot()
    set_inputs_count(chart, CODE, 200000)   # 2년치보다 크게 요청
    chart.BlockRequest()
    check_status(chart, "요청개수 방식 최초 요청")

    first = read_page(chart)
    page_sizes.append(len(first))
    for r in first:
        if (r[0], r[1]) not in seen:
            seen.add((r[0], r[1]))
            rows.append(r)

    cont = chart.Continue
    print(f"  page  1: 수신 {len(first):>6,}건  Continue={cont}  "
          f"범위 {fmt_span(first)}")
    print(f"  -> 요청 1회당 최대 수신 개수 = {len(first):,}건")

    if not cont:
        print("  -> Continue=0. 연속조회가 동작하지 않거나 데이터가 여기서 끝남.")

    page = 1
    stalled = 0
    while cont and page < MAX_PAGES:
        page += 1
        client.wait_for_request_slot()
        chart.BlockRequest()             # 입력값 재설정 없이 연속조회
        check_status(chart, f"연속조회 {page}페이지")

        batch = read_page(chart)
        page_sizes.append(len(batch))
        new = 0
        for r in batch:
            if (r[0], r[1]) not in seen:
                seen.add((r[0], r[1]))
                rows.append(r)
                new += 1
        cont = chart.Continue

        if page <= 3 or page % 20 == 0:
            print(f"  page {page:>2}: 수신 {len(batch):>6,}건  신규 {new:>6,}건  "
                  f"Continue={cont}  범위 {fmt_span(batch)}")

        # 같은 데이터만 계속 오면 페이징이 실제로는 안 도는 것
        if new == 0:
            stalled += 1
            if stalled >= 2:
                print(f"  -> page {page}: 신규 0건이 2회 연속. 페이징이 전진하지 않음.")
                break
        else:
            stalled = 0

    elapsed = time.time() - started
    rows.sort(key=lambda r: (r[0], r[1]))

    print(f"\n  결과: {page}회 요청 / 총 {len(rows):,}봉 / {elapsed:.1f}초")
    print(f"  실제 커버 기간: {fmt_span(rows)}")
    if page_sizes:
        print(f"  페이지당 수신: 최초 {page_sizes[0]:,} / "
              f"평균 {sum(page_sizes)//len(page_sizes):,}")
    print(f"  연속조회 동작 여부: {'O (동작함)' if page > 1 and len(rows) > page_sizes[0] else 'X (미동작)'}")
    return rows


# --------------------------------------------------------------------------
# TEST 3: 기간 방식으로 2년 경계 확인
# --------------------------------------------------------------------------
def probe_period_boundary(client):
    print("\n" + "=" * 72)
    print("[TEST 3] 기간 방식 — 1분봉이 실제로 어디서 잘리는지")
    print("=" * 72)

    chart = client.chart
    today = datetime.now()
    # 5년 전부터 요청. 공식 Q&A 대로면 2년에서 잘려야 한다.
    start = (today - timedelta(days=365 * 5)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    print(f"  요청 범위: {start} ~ {end} (5년)")

    client.wait_for_request_slot()
    set_inputs_period(chart, CODE, start, end)
    chart.BlockRequest()
    check_status(chart, "기간 방식 요청")

    first = read_page(chart)
    if not first:
        print("  -> 수신 0건")
        return

    # 데이터는 최신 -> 과거 순. 첫 페이지의 가장 과거 날짜부터 확인.
    oldest_first_page = min(r[0] for r in first)
    print(f"  page 1: 수신 {len(first):,}건  Continue={chart.Continue}  "
          f"범위 {fmt_span(first)}")

    # 페이징 끝까지 돌려 가장 오래된 날짜를 찾는다
    oldest = oldest_first_page
    page = 1
    seen_keys = {(r[0], r[1]) for r in first}
    while chart.Continue and page < MAX_PAGES:
        page += 1
        client.wait_for_request_slot()
        chart.BlockRequest()
        check_status(chart, f"기간 방식 연속조회 {page}")
        batch = read_page(chart)
        if not batch:
            break
        new = [r for r in batch if (r[0], r[1]) not in seen_keys]
        if not new:
            break
        seen_keys.update((r[0], r[1]) for r in new)
        oldest = min(oldest, min(r[0] for r in new))

    print(f"  -> 총 {page}회 요청, 가장 오래된 봉 날짜 = {oldest}")
    oldest_dt = datetime.strptime(str(oldest), "%Y%m%d")
    years = (today - oldest_dt).days / 365.0
    print(f"  -> 오늘 기준 {years:.2f}년 전까지 제공")
    print(f"  -> 공식 Q&A(2년) {'와 일치' if 1.7 <= years <= 2.3 else '와 불일치 — 재확인 필요'}")


# --------------------------------------------------------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    try:
        client = CybosClient(request_margin=2)
        client.ensure_connected()
    except (CybosError, ImportError) as exc:
        print(f"[중단] {exc}")
        sys.exit(1)

    name = client.code_to_name(CODE)
    print(f"프로브 대상: {CODE} {name}  |  {PERIOD_MIN}분봉")

    rows = probe_count_paging(client)

    if rows:
        with open(OUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["date", "time", "open", "high", "low", "close", "volume"])
            w.writerows(rows)
        size = os.path.getsize(OUT_FILE)
        print(f"\n  저장: {OUT_FILE}")
        print(f"  파일 크기: {size/1024/1024:.2f} MB  "
              f"(봉당 {size/max(len(rows),1):.1f} bytes)")

        # 전체 종목 추정 (보통주 약 2,600 기준)
        est = size * 2600 / 1024 / 1024 / 1024
        print(f"  -> 전체 2,600종목 동일 규모 가정 시 CSV 총량 ≈ {est:.1f} GB")

    try:
        probe_period_boundary(client)
    except CybosError as exc:
        print(f"  [TEST 3 실패] {exc}")


if __name__ == "__main__":
    main()
