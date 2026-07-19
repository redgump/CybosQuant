# -*- coding: utf-8 -*-
"""증분 업데이트 리허설.

전체 종목에 이어붙이기를 돌리기 전에, 한 종목의 **사본**을 상대로
실전과 똑같은 경로(마지막 봉 읽기 -> 개수 요청 -> 중복 필터 -> 이어붙이기)를
수행해 결과를 검증한다. 원본 CSV 는 건드리지 않는다.

새 거래일이 없으면 "이미 최신"으로 끝나 아무것도 검증하지 못하므로,
사본의 **꼬리를 일부러 잘라내** 장중에 끊긴 상황을 만든 뒤 이어붙이기가
원본과 바이트 단위로 같게 복구하는지 확인한다. 이게 통과하면
'덜 채워진 날 메우기'와 '중복 없는 이어붙이기'가 함께 검증된다.

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

    # 실전 코드가 사본을 보도록 경로만 갈아끼운다.
    cm.csv_path = lambda code: copy

    # --- 장중에 끊긴 상황을 만든다: 사본의 마지막 CUT 봉을 잘라낸다 ---
    CUT = 200
    with open(copy, encoding="utf-8-sig") as f:
        original_lines = f.read().splitlines()
    if len(original_lines) < CUT + 2:
        print("[중단] 표본이 너무 작습니다.")
        return 1
    origin_size = os.path.getsize(src)
    origin_last = cm.read_last_bar(copy)

    with open(copy, "w", newline="", encoding="utf-8-sig") as f:
        f.write("\r\n".join(original_lines[:-CUT]) + "\r\n")
    print(f"리허설 준비: 사본에서 마지막 {CUT}봉을 잘라냄")
    print(f"  원본 마지막 봉 {origin_last} / {origin_size:,} bytes")

    before_size = os.path.getsize(copy)

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

    # 실전(collect_minutes)과 동일하게 개수 방식으로 받는다.
    # 기간 방식은 종료일이 비거래일이면 0봉을 돌려주므로 쓰지 않는다.
    gap_days = (datetime.now() - datetime.strptime(str(last[0]), "%Y%m%d")).days + 1
    req_count = max(1000, min(gap_days * 500 + 500, config.COUNT))
    print(f"마지막 봉 이후 {gap_days}일 -> 최근 {req_count:,}봉 요청")

    rows = client.get_minute_bars(
        CODE,
        period_min=config.CHART_PERIOD_MIN,
        request_type="count",
        count=req_count,
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
        print("\n[결과] 잘라낸 구간을 되받지 못했습니다 — 이어붙이기가 동작하지 않음.")
        shutil.rmtree(work, ignore_errors=True)
        return 1

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

    after_size = os.path.getsize(copy)
    with open(copy, encoding="utf-8-sig") as f:
        restored_lines = f.read().splitlines()

    print("\n검증:")
    check(f"필드 수 이상 {bad_fields}개", bad_fields == 0)
    check("시간 오름차순 유지", keys == sorted(keys))
    check(f"중복 봉 없음 ({len(keys)-len(set(keys))}개)", len(keys) == len(set(keys)))
    check(f"잘라낸 {CUT}봉 복구 ({len(new_rows)}봉 추가)", len(new_rows) == CUT)
    check(f"행 수 원상복구 ({len(restored_lines)} = {len(original_lines)})",
          len(restored_lines) == len(original_lines))
    check(f"내용이 원본과 완전 일치", restored_lines == original_lines)
    check(f"파일 크기 원상복구 ({after_size:,} = {origin_size:,})",
          after_size == origin_size)
    check(f"마지막 봉 복원 {cm.read_last_bar(copy)} = {origin_last}",
          cm.read_last_bar(copy) == origin_last)
    check("원본 파일 미변경", os.path.getsize(src) == origin_size)

    print(f"\n사본 크기: {before_size:,} -> {after_size:,} bytes "
          f"(원본 {origin_size:,})")
    shutil.rmtree(work, ignore_errors=True)
    print("\n[결과] " + ("리허설 통과 — 전체 실행 가능" if ok else "리허설 실패 — 전체 실행 중단"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
