# -*- coding: utf-8 -*-
"""증분 업데이트 리허설.

전체 종목에 이어붙이기를 돌리기 전에, 한 종목의 **사본**을 상대로
실전과 똑같은 경로(마지막 봉 읽기 -> 기간 요청 -> 중복 필터 -> 이어붙이기)를
수행해 결과를 검증한다. 원본 CSV 는 건드리지 않는다.

이어붙이기는 되돌리기 번거로우므로 전체 실행 전에 이걸 먼저 통과시킨다.

    py32 probe_update.py
"""

import csv
import os
import shutil
import sys
import tempfile
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import config
import collect_minutes as cm
from cybos_client import CybosClient, CybosError

CODE = "A005930"


def main():
    src = os.path.join(config.OUTPUT_DIR, f"{CODE}_1m.csv")
    if not os.path.exists(src):
        print(f"[중단] 원본이 없습니다: {src}")
        return 1

    work = tempfile.mkdtemp(prefix="updprobe_")
    copy = os.path.join(work, os.path.basename(src))
    shutil.copy(src, copy)
    before_size = os.path.getsize(copy)

    # 실전 코드가 사본을 보도록 경로만 갈아끼운다.
    cm.csv_path = lambda code: copy

    try:
        client = CybosClient(request_margin=config.REQUEST_MARGIN)
        client.ensure_connected()
    except (CybosError, ImportError) as exc:
        print(f"[중단] {exc}")
        return 1

    last = cm.read_last_bar(copy)
    print(f"대상 {CODE} | 사본 {before_size/1024/1024:.2f} MB")
    print(f"마지막 봉: {last}")
    if last is None:
        print("[중단] 마지막 봉을 읽지 못했습니다.")
        return 1

    today = datetime.now().strftime("%Y%m%d")
    print(f"요청 기간: {last[0]} ~ {today}")

    rows = client.get_minute_bars(
        CODE,
        period_min=config.CHART_PERIOD_MIN,
        request_type="period",
        count=config.COUNT,
        start_date=str(last[0]),
        end_date=today,
        adjust_price=config.ADJUST_PRICE,
    )
    print(f"수신 {len(rows):,}봉 (범위 {rows[0][:2] if rows else '-'} ~ "
          f"{rows[-1][:2] if rows else '-'})")

    new_rows = [r for r in rows if (r[0], r[1]) > last]
    print(f"필터 후 신규 {len(new_rows):,}봉")
    if new_rows:
        print(f"  신규 범위: {new_rows[0][0]} {new_rows[0][1]:04d} ~ "
              f"{new_rows[-1][0]} {new_rows[-1][1]:04d}")

    if not new_rows:
        print("\n[결과] 추가할 새 데이터가 없습니다(이미 최신).")
        shutil.rmtree(work, ignore_errors=True)
        return 0

    cm.append_csv(CODE, new_rows)

    # ---- 검증: 사본을 통째로 읽어 무결성 확인 ----
    with open(copy, encoding="utf-8-sig") as f:
        body = list(csv.reader(f))[1:]
    keys = [(int(r[0]), int(r[1])) for r in body]
    bad_fields = sum(1 for r in body if len(r) != 7)
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print(("  PASS " if cond else "  FAIL ") + label)

    print("\n검증:")
    check(f"필드 수 이상 {bad_fields}개", bad_fields == 0)
    check("시간 오름차순 유지", keys == sorted(keys))
    check(f"중복 봉 없음 ({len(keys)-len(set(keys))}개)", len(keys) == len(set(keys)))
    check(f"행 수 = 기존+신규 ({len(keys)})",
          len(keys) == len(body))
    check(f"마지막 봉 갱신 {cm.read_last_bar(copy)}",
          cm.read_last_bar(copy) == (new_rows[-1][0], new_rows[-1][1]))
    check(f"원본 미변경 ({os.path.getsize(src)} bytes)",
          os.path.getsize(src) == before_size)

    print(f"\n사본 크기: {before_size:,} -> {os.path.getsize(copy):,} bytes")
    shutil.rmtree(work, ignore_errors=True)
    print("\n[결과] " + ("리허설 통과 — 전체 실행 가능" if ok else "리허설 실패 — 전체 실행 중단"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
