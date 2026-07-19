# -*- coding: utf-8 -*-
"""CYBOS 세션 유지 + 만료 시점 실측.

대신증권 안내는 "일정시간 동안 거래가 없을 경우 자동으로 접속이 종료된다"
라고만 하고 구체적인 시간을 밝히지 않는다. 무활동 타임아웃이라면 주기적으로
가벼운 요청을 보내는 것으로 세션을 살려둘 수 있다.

이 스크립트는 두 가지를 동시에 한다.

  1) 유지: INTERVAL_SEC 마다 시세를 1건 조회해 '활동'을 만든다.
     (IsConnect 조회만으로는 로컬 상태만 보므로 실제 요청을 보낸다.)
  2) 측정: 매 시도의 시각과 결과를 CSV 로 남긴다. 끊기면 그 시점이
     기록되므로, 유지가 실패하더라도 '언제 끊기는지'를 알게 된다.

절전으로 PC 가 잠들면 의미가 없으므로 실행 중 절전을 막는다.

    py32 keepalive.py          # Ctrl+C 로 중단

결과는 keepalive.csv 에 누적된다:
    timestamp,elapsed_hours,connected,bars,note
"""

import csv
import os
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import config
from collect_minutes import prevent_sleep
from cybos_client import CybosClient, CybosError

# 요청 주기(초). 무활동 임계값을 모르므로 보수적으로 짧게 잡는다.
# 5분마다 1건이면 하루 288건으로, 15초당 60건 제한에 전혀 부담이 없다.
INTERVAL_SEC = 300

# 활동을 만들 종목. 거래정지 위험이 없는 대형주로 고정한다.
PING_CODE = "A005930"

OUT_CSV = "keepalive.csv"


def log_row(path, row):
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp", "elapsed_hours", "connected", "bars", "note"])
        w.writerow(row)


def main():
    prevent_sleep(True)
    print(f"세션 유지 시작 | 주기 {INTERVAL_SEC}초 | 기록 {OUT_CSV}")
    print("Ctrl+C 로 중단합니다.\n")

    try:
        client = CybosClient(request_margin=config.REQUEST_MARGIN)
    except (CybosError, ImportError) as exc:
        print(f"[중단] {exc}")
        return 1

    started = time.time()
    lost_at = None
    n = 0

    while True:
        now = datetime.now()
        elapsed = (time.time() - started) / 3600.0
        connected = client.is_connected()
        bars, note = 0, ""

        if connected:
            # IsConnect 만으로는 서버와 통신하지 않을 수 있으므로
            # 실제 시세를 1건 요청해 '거래 활동'을 만든다.
            try:
                rows = client.get_minute_bars(
                    PING_CODE, period_min=1, request_type="count", count=1,
                    adjust_price=config.ADJUST_PRICE,
                )
                bars = len(rows)
                note = "ok" if bars else "요청 성공했으나 0봉"
            except CybosError as exc:
                note = f"요청 실패: {exc}"
        else:
            note = "연결 끊김"
            if lost_at is None:
                lost_at = now
                print(f"\n[!] {now:%m-%d %H:%M:%S} 연결이 끊어졌습니다. "
                      f"유지 {elapsed:.2f}시간 만에 만료.")
                print("    CYBOS Plus 에 다시 로그인하면 자동으로 재개합니다.\n")

        if connected and lost_at is not None:
            print(f"[+] {now:%m-%d %H:%M:%S} 연결 복구됨 "
                  f"(끊김 {(now-lost_at).total_seconds()/60:.0f}분)")
            lost_at = None

        log_row(OUT_CSV, [now.strftime("%Y-%m-%d %H:%M:%S"),
                          f"{elapsed:.3f}", int(connected), bars, note])

        n += 1
        if n % 12 == 1 or not connected:   # 1시간마다 + 문제 시 출력
            print(f"  {now:%m-%d %H:%M:%S} | 경과 {elapsed:5.2f}h | "
                  f"연결 {'O' if connected else 'X'} | {note}")

        try:
            time.sleep(INTERVAL_SEC)
        except KeyboardInterrupt:
            print(f"\n중단. 총 {elapsed:.2f}시간 관측, 기록은 {OUT_CSV} 에 남았습니다.")
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n중단.")
    finally:
        prevent_sleep(False)
