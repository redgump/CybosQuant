# -*- coding: utf-8 -*-
"""전체 종목 분봉 수집기.

CYBOS Plus 로 대상 종목의 분봉을 조회해 종목별 CSV 로 저장한다.
32비트 Python + 실행/로그인된 CYBOS Plus 환경에서 실행할 것.

    python collect_minutes.py
"""

import csv
import os
import sys
import time

# Windows 콘솔 한글 깨짐 방지 (출력 스트림을 UTF-8 로 재설정)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import config
from cybos_client import CybosClient, CybosError


def csv_path(code):
    fname = f"{code}_{config.CHART_PERIOD_MIN}m.csv"
    return os.path.join(config.OUTPUT_DIR, fname)


def save_csv(code, rows):
    """분봉 행들을 종목별 CSV 로 저장한다 (시간 오름차순)."""
    path = csv_path(code)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "time", "open", "high", "low", "close", "volume"])
        writer.writerows(rows)


def main():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    try:
        client = CybosClient(request_margin=config.REQUEST_MARGIN)
        client.ensure_connected()
    except (CybosError, ImportError) as exc:
        print(f"[중단] {exc}")
        sys.exit(1)

    codes = client.get_stock_codes(
        markets=config.MARKETS,
        common_only=config.COMMON_STOCK_ONLY,
    )
    if config.LIMIT_STOCKS > 0:
        codes = codes[: config.LIMIT_STOCKS]

    total = len(codes)
    print(f"대상 종목: {total}개  |  분봉주기: {config.CHART_PERIOD_MIN}분  "
          f"|  요청방식: {config.REQUEST_TYPE}")

    started = time.time()
    ok = skipped = failed = 0

    for idx, code in enumerate(codes, start=1):
        name = client.code_to_name(code)
        prefix = f"[{idx}/{total}] {code} {name}"

        if config.SKIP_EXISTING and os.path.exists(csv_path(code)):
            skipped += 1
            print(f"{prefix} -> 건너뜀(기존 파일)")
            continue

        try:
            rows = client.get_minute_bars(
                code,
                period_min=config.CHART_PERIOD_MIN,
                request_type=config.REQUEST_TYPE,
                count=config.COUNT,
                start_date=config.START_DATE,
                end_date=config.END_DATE,
                adjust_price=config.ADJUST_PRICE,
            )
        except CybosError as exc:
            failed += 1
            print(f"{prefix} -> 실패: {exc}")
            continue
        except KeyboardInterrupt:
            print("\n사용자 중단. 지금까지 저장된 파일은 유지됩니다. "
                  "다시 실행하면 이어서 진행합니다(SKIP_EXISTING=True).")
            break

        if not rows:
            skipped += 1
            print(f"{prefix} -> 데이터 없음")
            continue

        save_csv(code, rows)
        ok += 1
        print(f"{prefix} -> {len(rows)}건 저장")

    elapsed = time.time() - started
    print("\n===== 완료 =====")
    print(f"저장 {ok} / 건너뜀 {skipped} / 실패 {failed}  "
          f"(총 {total}, 소요 {elapsed/60:.1f}분)")


if __name__ == "__main__":
    main()
