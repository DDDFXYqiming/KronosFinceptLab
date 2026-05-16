"""
BaoStock Data Source Adapter
Supports A-share historical data, financial data, etc.
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime

from . import DataSource, DataSourceConfig, DataSourceStatus


class BaoStockSource(DataSource):
    """BaoStock Data Source"""

    supported_endpoints = {
        "stock_zh_a_hist",
        "stock_info_a_code_name",
        "stock_individual_info_em",
    }

    def __init__(self, priority: int = 2):
        config = DataSourceConfig(
            name="baostock",
            priority=priority,
            max_retries=3,
            retry_delay=1.0,
            timeout=30.0,
            circuit_break_threshold=5,
            circuit_break_duration=300,
            health_check_interval=60
        )
        super().__init__(config)
        self._bs = None
        self._logged_in = False

    def _get_bs(self):
        """Lazy-load BaoStock"""
        if self._bs is None:
            try:
                import baostock as bs
                self._bs = bs
            except ImportError as e:
                raise ImportError(f"BaoStock 未安装: {e}")
        return self._bs

    def _login(self):
        """Log in to BaoStock"""
        if not self._logged_in:
            bs = self._get_bs()
            lg = bs.login()
            if lg.error_code != "0":
                raise RuntimeError(f"BaoStock 登录失败: {lg.error_msg}")
            self._logged_in = True

    def _logout(self):
        """Log out of BaoStock"""
        if self._logged_in:
            bs = self._get_bs()
            try:
                bs.logout()
            finally:
                self._logged_in = False

    def _query_to_list(self, rs) -> list:
        """Convert query results to a list"""
        if rs.error_code != "0":
            raise RuntimeError(rs.error_msg)

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        return rows

    def _normalize_code(self, symbol: str) -> str:
        """
        Normalize stock code

        Args:
            symbol: Stock code (e.g., '601398')

        Returns:
            BaoStock-format code (e.g., 'sh.601398')
        """
        # If it already has a market prefix, return directly
        if '.' in symbol:
            return symbol

        # Determine market based on code prefix
        if symbol.startswith('6'):
            return f"sh.{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            return f"sz.{symbol}"
        elif symbol.startswith('4') or symbol.startswith('8'):
            return f"bj.{symbol}"
        else:
            # Default to Shanghai
            return f"sh.{symbol}"

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch data

        Args:
            endpoint: Data endpoint
            **kwargs: Parameters passed to BaoStock functions

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (if failed),
                "source": str,
                "timestamp": int
            }
        """
        try:
            self._login()
            bs = self._get_bs()

            start_time = time.time()
            data = None

            # Call the corresponding function based on the endpoint
            if endpoint == "stock_zh_a_hist":
                # Fetch historical K-line data
                symbol = kwargs.get("symbol", "")
                code = self._normalize_code(symbol)
                start_date = kwargs.get("start_date", "2020-01-01")
                end_date = kwargs.get("end_date", datetime.now().strftime('%Y-%m-%d'))
                frequency = kwargs.get("frequency", "d")  # d=daily, w=weekly, m=monthly
                adjustflag = kwargs.get("adjustflag", "3")  # 1=backward adjusted, 2=forward adjusted, 3=unadjusted

                # Convert date format (from YYYYMMDD to YYYY-MM-DD)
                if len(start_date) == 8:
                    start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
                if len(end_date) == 8:
                    end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

                fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST"
                rs = bs.query_history_k_data_plus(
                    code=code,
                    fields=fields,
                    start_date=start_date,
                    end_date=end_date,
                    frequency=frequency,
                    adjustflag=adjustflag
                )
                rows = self._query_to_list(rs)

                # Convert to a format compatible with AkShare
                data = []
                for row in rows:
                    if len(row) >= 14:
                        data.append({
                            "日期": row[0],
                            "股票代码": row[1],
                            "开盘": float(row[2]) if row[2] else 0,
                            "最高": float(row[3]) if row[3] else 0,
                            "最低": float(row[4]) if row[4] else 0,
                            "收盘": float(row[5]) if row[5] else 0,
                            "成交量": int(float(row[7])) if row[7] else 0,
                            "成交额": float(row[8]) if row[8] else 0,
                            "振幅": 0,  # Not provided by BaoStock
                            "涨跌幅": float(row[12]) if row[12] else 0,
                            "涨跌额": 0,  # Not provided by BaoStock
                            "换手率": float(row[10]) if row[10] else 0
                        })

            elif endpoint == "stock_info_a_code_name":
                # Fetch stock list
                rs = bs.query_stock_basic()
                rows = self._query_to_list(rs)
                data = []
                for row in rows:
                    if len(row) >= 7:
                        data.append({
                            "code": row[0],
                            "code_name": row[1],  # Use code_name field name
                            "ipoDate": row[3],
                            "outDate": row[4],
                            "type": row[5],
                            "status": row[6]
                        })

            elif endpoint == "stock_individual_info_em":
                # Fetch individual stock info
                symbol = kwargs.get("symbol", "")
                code = self._normalize_code(symbol)
                rs = bs.query_stock_basic(code=code)
                rows = self._query_to_list(rs)
                if rows:
                    row = rows[0]
                    data = {
                        "股票代码": row[0],
                        "股票名称": row[1],
                        "上市日期": row[3],
                        "退市日期": row[4],
                        "股票类型": row[5],
                        "股票状态": row[6]
                    }
                else:
                    data = None

            else:
                return {
                    "success": False,
                    "data": None,
                    "error": f"未知的 BaoStock 端点: {endpoint}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            elapsed = time.time() - start_time

            if data is None:
                return {
                    "success": False,
                    "data": None,
                    "error": "返回数据为空",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            return {
                "success": True,
                "data": data,
                "count": len(data) if isinstance(data, list) else 1,
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
                "elapsed": round(elapsed, 2)
            }

        except Exception as e:
            # Log out to clean up connections
            self._logout()
            return {
                "success": False,
                "data": None,
                "error": f"{type(e).__name__}: {str(e)}",
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp())
            }

    def __del__(self):
        """Log out during destruction"""
        self._logout()
