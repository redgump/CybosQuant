# -*- coding: utf-8 -*-
"""CYBOS Plus COM API 얇은 래퍼.

반드시 32비트 Python + 실행/로그인된 CYBOS Plus 환경에서만 동작한다.
64비트 Python 에서는 win32com 이 COM 객체를 로드하지 못한다.
"""

import time

try:
    import win32com.client
except ImportError as exc:  # pragma: no cover - 환경 안내용
    raise ImportError(
        "win32com(pywin32)을 불러올 수 없습니다. 32비트 Python 에서 "
        "'pip install pywin32' 로 설치했는지 확인하세요."
    ) from exc


# GetLimitRemainCount 의 요청 종류 상수
LT_TRADE_REQUEST = 0      # 주문 관련
LT_NONTRADE_REQUEST = 1   # 시세 조회 (분봉 조회가 여기에 해당)
LT_SUBSCRIBE = 2          # 실시간 구독


class CybosError(RuntimeError):
    """CYBOS 조회 실패 시 발생."""


class CybosClient:
    """연결 확인, 요청제한 관리, 종목 리스트, 분봉 조회를 담당한다."""

    def __init__(self, request_margin=2):
        self.request_margin = request_margin
        self.cybos = win32com.client.Dispatch("CpUtil.CpCybos")
        self.code_mgr = win32com.client.Dispatch("CpUtil.CpCodeMgr")
        self.chart = win32com.client.Dispatch("CpSysDib.StockChart")

    # ------------------------------------------------------------------ 연결
    def ensure_connected(self):
        """CYBOS Plus 연결 상태를 확인한다. 끊겨 있으면 예외."""
        if self.cybos.IsConnect != 1:
            raise CybosError(
                "CYBOS Plus 에 연결되어 있지 않습니다. "
                "CYBOS Plus 를 관리자 권한으로 실행하고 로그인했는지 확인하세요."
            )

    # -------------------------------------------------------------- 요청제한
    def wait_for_request_slot(self):
        """시세요청 잔여 건수가 여유분 이하로 떨어지면 제한이 풀릴 때까지 대기."""
        remain = self.cybos.GetLimitRemainCount(LT_NONTRADE_REQUEST)
        if remain <= self.request_margin:
            wait_ms = self.cybos.LimitRequestRemainTime
            # 여유를 위해 살짝 더 대기
            time.sleep(max(wait_ms, 0) / 1000.0 + 0.2)

    # --------------------------------------------------------------- 종목목록
    def get_stock_codes(self, markets=(1, 2), common_only=True):
        """대상 시장의 종목코드 리스트를 반환한다.

        markets: 1=코스피(거래소), 2=코스닥
        common_only: True 면 보통주(주권)만, ETF/ETN/스팩 등 제외
        """
        codes = []
        for market in markets:
            for code in self.code_mgr.GetStockListByMarket(market):
                if common_only and not self._is_common_stock(code):
                    continue
                codes.append(code)
        return codes

    def _is_common_stock(self, code):
        """보통주(주권) 여부. ETF/ETN/스팩/우선주 제외 필터."""
        # GetStockSectionKind: 1 = 주권(일반 주식)
        if self.code_mgr.GetStockSectionKind(code) != 1:
            return False
        # 스팩(기업인수목적회사) 제외
        try:
            if self.code_mgr.IsSPAC(code):
                return False
        except Exception:
            pass
        return True

    def code_to_name(self, code):
        return self.code_mgr.CodeToName(code)

    # --------------------------------------------------------------- 분봉조회
    def get_minute_bars(
        self,
        code,
        period_min=1,
        request_type="count",
        count=2000,
        start_date="",
        end_date="",
        adjust_price=True,
    ):
        """지정 종목의 분봉을 조회해 시간 오름차순 리스트로 반환한다.

        반환: [(date, time, open, high, low, close, volume), ...]
              date = YYYYMMDD(int), time = HHMM(int)
        연속조회(Continue)를 통해 count/기간 조건을 채울 때까지 페이징한다.
        """
        rows = []
        seen = set()
        is_continue = False

        while True:
            self.wait_for_request_slot()
            self._set_chart_inputs(
                code, period_min, request_type, count,
                start_date, end_date, adjust_price, is_continue,
            )
            self.chart.BlockRequest()

            status = self.chart.GetDibStatus()
            if status != 0:
                msg = self.chart.GetDibMsg1()
                raise CybosError(f"{code} 조회 실패 (status={status}): {msg}")

            received = self.chart.GetHeaderValue(3)  # 수신 개수
            # 데이터는 최신 -> 과거 순. 뒤에서부터 읽어 시간 오름차순 누적.
            batch = []
            for i in range(received):
                row = (
                    self.chart.GetDataValue(0, i),  # 날짜
                    self.chart.GetDataValue(1, i),  # 시간
                    self.chart.GetDataValue(2, i),  # 시가
                    self.chart.GetDataValue(3, i),  # 고가
                    self.chart.GetDataValue(4, i),  # 저가
                    self.chart.GetDataValue(5, i),  # 종가
                    self.chart.GetDataValue(6, i),  # 거래량
                )
                key = (row[0], row[1])
                if key in seen:
                    continue
                seen.add(key)
                batch.append(row)
            rows.extend(batch)

            # count 방식: 목표 개수 도달 시 종료
            if request_type == "count" and len(rows) >= count:
                break
            # 더 받을 데이터가 없으면 종료
            if self.chart.Continue == 0:
                break
            is_continue = True

        rows.sort(key=lambda r: (r[0], r[1]))
        if request_type == "count" and len(rows) > count:
            rows = rows[-count:]
        return rows

    def _set_chart_inputs(
        self, code, period_min, request_type, count,
        start_date, end_date, adjust_price, is_continue,
    ):
        # 연속조회 시에는 종목코드만 유지하고 나머지 입력은 그대로 재요청한다.
        if is_continue:
            return

        self.chart.SetInputValue(0, code)  # 종목코드 (예: 'A005930')
        if request_type == "period":
            self.chart.SetInputValue(1, ord("1"))          # 요청구분: 기간
            self.chart.SetInputValue(2, int(end_date))     # 종료일
            self.chart.SetInputValue(3, int(start_date))   # 시작일
        else:
            self.chart.SetInputValue(1, ord("2"))          # 요청구분: 개수
            self.chart.SetInputValue(4, count)             # 요청개수
        # 필드: 날짜, 시간, 시가, 고가, 저가, 종가, 거래량
        self.chart.SetInputValue(5, [0, 1, 2, 3, 4, 5, 8])
        self.chart.SetInputValue(6, ord("m"))              # 차트종류: 분
        self.chart.SetInputValue(7, period_min)            # 분 주기
        self.chart.SetInputValue(9, ord("1") if adjust_price else ord("0"))
