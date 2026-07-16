# -*- coding: utf-8 -*-
"""전체 종목 분봉 수집기.

CYBOS Plus 로 대상 종목의 분봉을 조회해 종목별 CSV 로 저장한다.
32비트 Python + 실행/로그인된 CYBOS Plus 환경에서 실행할 것.

    python collect_minutes.py
"""

import csv
import ctypes
import os
import sys
import time
from datetime import datetime

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
    """분봉 행들을 종목별 CSV 로 저장한다 (시간 오름차순).

    임시 파일에 먼저 쓰고 교체한다. 도중에 죽어도 반쪽짜리 CSV 가
    남지 않아야 SKIP_EXISTING 재개가 그 종목을 건너뛰지 않는다.
    """
    path = csv_path(code)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "time", "open", "high", "low", "close", "volume"])
        writer.writerows(rows)
    os.replace(tmp, path)


# SetThreadExecutionState 플래그 (WinBase.h)
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def prevent_sleep(enable):
    """실행 중 PC 절전 진입을 막는다 (프로세스 종료 시 자동 해제).

    시스템 전원 설정을 바꾸지 않고 현재 스레드에만 적용한다.
    """
    try:
        state = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if enable else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(state)
        return True
    except Exception:
        return False


def fmt_eta(done, total, elapsed):
    """남은 시간 추정 문자열."""
    if done <= 0:
        return "-"
    remain = elapsed / done * (total - done)
    eta = datetime.fromtimestamp(time.time() + remain)
    return f"잔여 {remain/3600:.1f}시간 (예상 완료 {eta:%m-%d %H:%M})"


def main():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    if config.PREVENT_SLEEP and prevent_sleep(True):
        print("[안내] 실행 중 PC 절전 진입을 막습니다 (종료 시 자동 해제).")

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
    consecutive_failures = 0
    aborted = None
    processed = 0  # 실제로 조회를 시도한 종목 수 (ETA 계산용)

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
            consecutive_failures += 1
            print(f"{prefix} -> 실패: {exc}")

            # 연결이 끊긴 것이라면, 남은 종목을 전부 '실패'로 태우지 않는다.
            # 복구를 기다렸다가 살아나면 이어가고, 끝내 안 되면 중단한다.
            if not client.is_connected():
                print(f"  [경고] CYBOS 연결이 끊어졌습니다. "
                      f"최대 {config.RECONNECT_WAIT_SEC/60:.0f}분 대기하며 복구를 확인합니다. "
                      f"CYBOS Plus 에 다시 로그인하면 자동으로 재개합니다.")
                recovered = client.wait_for_reconnect(
                    timeout_sec=config.RECONNECT_WAIT_SEC,
                    poll_sec=config.RECONNECT_POLL_SEC,
                    on_wait=lambda e, t: print(
                        f"  ... 재연결 대기 {e/60:.1f}/{t/60:.0f}분"),
                )
                if not recovered:
                    aborted = ("CYBOS 연결이 복구되지 않아 중단합니다.")
                    break
                print("  [복구] 연결이 돌아왔습니다. 수집을 재개합니다.")
                consecutive_failures = 0
            elif consecutive_failures >= config.MAX_CONSECUTIVE_FAILURES:
                # 연결은 살아 있는데 계속 실패 -> 개별 종목 문제가 아니다.
                aborted = (f"연결은 정상이나 {consecutive_failures}종목 연속 실패하여 "
                           f"중단합니다.")
                break
            continue
        except KeyboardInterrupt:
            aborted = "사용자 중단(Ctrl+C)."
            break

        consecutive_failures = 0
        processed += 1

        if not rows:
            skipped += 1
            print(f"{prefix} -> 데이터 없음")
            continue

        save_csv(code, rows)
        ok += 1
        print(f"{prefix} -> {len(rows):,}건 저장")

        if processed % 50 == 0:
            print(f"  --- 진행 {idx}/{total} | 저장 {ok} 실패 {failed} | "
                  f"{fmt_eta(idx, total, time.time() - started)}")

    elapsed = time.time() - started
    print("\n===== 완료 =====" if not aborted else f"\n===== 중단: {aborted} =====")
    print(f"저장 {ok} / 건너뜀 {skipped} / 실패 {failed}  "
          f"(총 {total}, 소요 {elapsed/3600:.2f}시간)")
    if aborted:
        print("이미 저장된 CSV 는 유지됩니다. "
              "원인을 해결하고 다시 실행하면 이어서 진행합니다(SKIP_EXISTING=True).")
    return 1 if aborted else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        prevent_sleep(False)
