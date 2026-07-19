# -*- coding: utf-8 -*-
"""증분 업데이트의 두 가지 전제 검증 + 소요 시간 실측.

[검증 1] 기간(period) 요청이 '시작일 당일'을 포함하는가?
    증분은 마지막 봉이 있는 날짜부터 다시 요청해, 장중에 끊겨 덜 채워진
    날의 나머지를 메우는 설계다. 시작일이 배타적으로 처리되면 그 날의
    남은 봉을 영영 못 받게 되므로 반드시 확인해야 한다.

[검증 2] 마지막 거래일이 언제인가? (개수 방식 기준)

[측정] 종목당 1회 요청에 걸리는 시간 -> 전체 소요 추정

    py32 probe_diag.py
"""

import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import config
from cybos_client import CybosClient, CybosError

CODE = "A005930"


def main():
    try:
        client = CybosClient(request_margin=config.REQUEST_MARGIN)
        client.ensure_connected()
    except (CybosError, ImportError) as exc:
        print(f"[중단] {exc}")
        return 1

    print(f"진단 대상 {CODE} | 오늘 {datetime.now():%Y-%m-%d(%a)}")

    # ------------------------------------------------ 검증 2: 마지막 거래일
    print("\n[검증 2] 개수 방식으로 최근 500봉 -> 마지막 거래일 확인")
    rows = client.get_minute_bars(
        CODE, period_min=1, request_type="count", count=500,
        adjust_price=config.ADJUST_PRICE,
    )
    dates = sorted({r[0] for r in rows})
    print(f"  수신 {len(rows)}봉 | 포함 날짜 {dates}")
    print(f"  마지막 거래일 = {dates[-1] if dates else '-'}")

    # ------------------------------------------- 검증 1: 시작일 포함 여부
    # 마지막 거래일을 시작일로 줬을 때 그 날 데이터가 오는지 본다.
    last_day = dates[-1]
    print(f"\n[검증 1] 기간 요청이 시작일({last_day}) 당일을 포함하는가")
    cases = [
        ("시작일=마지막거래일, 종료=오늘", last_day, int(datetime.now().strftime("%Y%m%d"))),
        ("시작일=종료일=마지막거래일", last_day, last_day),
        ("시작일=하루전, 종료=마지막거래일", dates[-2] if len(dates) > 1 else last_day, last_day),
    ]
    include_ok = None
    for label, s, e in cases:
        try:
            r = client.get_minute_bars(
                CODE, period_min=1, request_type="period",
                start_date=str(s), end_date=str(e),
                adjust_price=config.ADJUST_PRICE,
            )
            got = sorted({x[0] for x in r})
            has_start = last_day in got
            if include_ok is None:
                include_ok = has_start
            print(f"  {label:28s} ({s}~{e}) -> {len(r):>6,}봉 | 날짜 {got}"
                  f" | 시작일포함 {'O' if has_start else 'X'}")
        except CybosError as exc:
            print(f"  {label:28s} ({s}~{e}) -> 실패: {exc}")

    # ---------------------------------------------------- 측정: 요청 속도
    print("\n[측정] 증분 1회 요청 소요 시간 (20종목 표본)")
    codes = client.get_stock_codes(markets=config.MARKETS,
                                   common_only=config.COMMON_STOCK_ONLY)
    total_codes = len(codes)
    sample = codes[:20]
    t0 = time.time()
    for c in sample:
        try:
            client.get_minute_bars(
                c, period_min=1, request_type="period",
                start_date=str(last_day),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust_price=config.ADJUST_PRICE,
            )
        except CybosError:
            pass
    per = (time.time() - t0) / len(sample)
    print(f"  종목당 평균 {per:.2f}초")
    print(f"  전체 {total_codes:,}종목 추정: {per*total_codes/60:.1f}분")

    print("\n[판정]")
    if include_ok:
        print("  시작일 당일이 포함된다 -> 장중 끊김 복구 설계가 성립한다.")
    else:
        print("  시작일 당일이 오지 않는다 -> 덜 채워진 날을 못 메운다.")
        print("  증분 요청 시작일을 하루 앞당겨야 한다(collect_minutes 수정 필요).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
