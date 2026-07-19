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


CSV_HEADER = ["date", "time", "open", "high", "low", "close", "volume"]


def save_csv(code, rows):
    """분봉 행들을 종목별 CSV 로 저장한다 (시간 오름차순).

    임시 파일에 먼저 쓰고 교체한다. 도중에 죽어도 반쪽짜리 CSV 가
    남지 않아야 SKIP_EXISTING 재개가 그 종목을 건너뛰지 않는다.
    """
    path = csv_path(code)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    os.replace(tmp, path)


def read_last_bar(path, tail_bytes=8192):
    """CSV 의 마지막 봉 (date, time) 을 읽어 반환한다. 없으면 None.

    파일이 수 MB 라 전체를 읽지 않고 끝부분만 확인한다.
    이어붙이기 도중 중단되어 마지막 줄이 잘렸을 수 있으므로, 깨진
    꼬리 줄은 잘라내고(파일을 직접 고친다) 그 앞의 온전한 줄을 쓴다.
    """
    size = os.path.getsize(path)
    if size == 0:
        return None

    with open(path, "rb") as f:
        start = max(0, size - tail_bytes)
        f.seek(start)
        chunk = f.read()

    # 첫 줄은 잘렸을 수 있으니 버린다(파일 처음부터 읽은 경우는 제외).
    lines = chunk.split(b"\n")
    if start > 0:
        lines = lines[1:]

    # 뒤에서부터 온전한 줄을 찾는다. split(b"\n") 결과에서 마지막 원소만
    # 뒤따르는 개행이 없고(파일이 개행으로 끝나면 그 원소는 빈 문자열),
    # 나머지는 개행 1바이트를 동반한다. 이걸 구분하지 않으면 truncate 위치가
    # 1바이트 어긋나 파일 끝 개행이 사라지고, 다음 이어붙이기가 마지막 줄에
    # 달라붙어 데이터를 망가뜨린다.
    offset = size
    for i, raw in enumerate(reversed(lines)):
        nl = 0 if i == 0 else 1
        offset -= len(raw) + nl        # 이 줄이 시작하는 위치
        line = raw.strip()
        if not line:
            continue
        parts = line.decode("utf-8", errors="replace").split(",")
        if len(parts) == len(CSV_HEADER):
            try:
                date, tm = int(parts[0]), int(parts[1])
            except ValueError:
                continue               # 헤더 줄
            if nl == 0:
                # 파일이 개행 없이 끝났다 -> 뒤의 쓰레기를 버리고 개행 보충
                with open(path, "r+b") as f:
                    f.seek(offset + len(raw))
                    f.truncate()
                    f.write(b"\r\n")
            elif offset + len(raw) + nl < size:
                # 마지막 온전한 줄 뒤에 잘린 꼬리가 남아 있다 -> 잘라낸다
                with open(path, "r+b") as f:
                    f.truncate(offset + len(raw) + nl)
            return date, tm
    return None


def append_csv(code, rows):
    """기존 CSV 뒤에 새 봉들을 이어붙인다 (헤더 없이).

    한 번의 write 로 내보내 중단 시 잘린 줄이 남을 창을 줄인다.
    그래도 잘리면 다음 실행의 read_last_bar() 가 정리한다.
    """
    path = csv_path(code)
    buf = "".join(",".join(str(v) for v in r) + "\r\n" for r in rows)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        f.write(buf)


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
    updated = uptodate = 0
    consecutive_failures = 0
    aborted = None
    processed = 0  # 실제로 조회를 시도한 종목 수 (ETA 계산용)
    today_str = datetime.now().strftime("%Y%m%d")

    for idx, code in enumerate(codes, start=1):
        name = client.code_to_name(code)
        prefix = f"[{idx}/{total}] {code} {name}"

        exists = os.path.exists(csv_path(code))
        last_bar = None

        if exists:
            if config.INCREMENTAL_UPDATE:
                # 마지막 봉 이후만 받아 이어붙인다.
                last_bar = read_last_bar(csv_path(code))
                if last_bar is None:
                    # 파일이 비었거나 헤더뿐 -> 전체 수집으로 되돌린다.
                    exists = False
            elif config.SKIP_EXISTING:
                skipped += 1
                print(f"{prefix} -> 건너뜀(기존 파일)")
                continue

        if last_bar is not None:
            # 마지막 봉이 있는 날부터 오늘까지 요청한다. 그 날 장중에
            # 수집이 끊겼더라도 남은 봉이 함께 채워진다.
            req_type = "period"
            req_start = str(last_bar[0])
            req_end = today_str
        else:
            req_type = config.REQUEST_TYPE
            req_start = config.START_DATE
            req_end = config.END_DATE

        try:
            rows = client.get_minute_bars(
                code,
                period_min=config.CHART_PERIOD_MIN,
                request_type=req_type,
                count=config.COUNT,
                start_date=req_start,
                end_date=req_end,
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

        if last_bar is not None:
            # 이미 가진 마지막 봉보다 뒤엣것만 남긴다(같은 날 중복 방지).
            new_rows = [r for r in rows if (r[0], r[1]) > last_bar]
            if not new_rows:
                uptodate += 1
                print(f"{prefix} -> 최신 상태({last_bar[0]} {last_bar[1]:04d})")
                continue
            append_csv(code, new_rows)
            updated += 1
            print(f"{prefix} -> {len(new_rows):,}건 추가 "
                  f"(~{new_rows[-1][0]} {new_rows[-1][1]:04d})")
        else:
            save_csv(code, rows)
            ok += 1
            print(f"{prefix} -> {len(rows):,}건 저장")

        if processed % 50 == 0:
            print(f"  --- 진행 {idx}/{total} | 추가 {updated} 최신 {uptodate} "
                  f"신규저장 {ok} 실패 {failed} | "
                  f"{fmt_eta(idx, total, time.time() - started)}")

    elapsed = time.time() - started
    print("\n===== 완료 =====" if not aborted else f"\n===== 중단: {aborted} =====")
    if config.INCREMENTAL_UPDATE:
        print(f"추가 {updated} / 이미최신 {uptodate} / 신규저장 {ok} / "
              f"건너뜀 {skipped} / 실패 {failed}  "
              f"(총 {total}, 소요 {elapsed/3600:.2f}시간)")
    else:
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
