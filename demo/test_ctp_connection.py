# -*- coding: utf-8 -*-
"""CTP 交易前置连接测试脚本。

用法示例：
python demo/test_ctp_connection.py \
  --front tcp://180.168.146.187:10000 \
  --broker 9999 \
  --user 000000 \
  --password 123456

也支持通过环境变量传参：
CTP_FRONT_ADDR / CTP_BROKER_ID / CTP_USER_ID / CTP_PASSWORD
"""

import argparse
import os
import threading
import time

import thosttraderapi as api


class TraderConnectionTester(api.CThostFtdcTraderSpi):
    """只做连接与登录验证，不做下单。"""

    def __init__(self, trader_api, broker_id, user_id, password):
        super().__init__()
        self.trader_api = trader_api
        self.broker_id = broker_id
        self.user_id = user_id
        self.password = password

        self.done = threading.Event()
        self.success = False
        self.error_msg = ""

    def finish(self, success, message):
        if not self.done.is_set():
            self.success = success
            self.error_msg = message
            self.done.set()

    def OnFrontConnected(self) -> "void":
        print("[CTP] OnFrontConnected: 前置已连接，开始发送登录请求")
        login = api.CThostFtdcReqUserLoginField()
        login.BrokerID = self.broker_id
        login.UserID = self.user_id
        login.Password = self.password
        login.UserProductInfo = "python-ctpapi-connection-test"

        ret = self.trader_api.ReqUserLogin(login, 1)
        if ret != 0:
            self.finish(False, f"ReqUserLogin 调用失败，返回码={ret}")

    def OnFrontDisconnected(self, nReason: "int") -> "void":
        self.finish(False, f"OnFrontDisconnected: 与前置断开，原因码={nReason}")

    def OnRspUserLogin(
        self,
        pRspUserLogin: "CThostFtdcRspUserLoginField",
        pRspInfo: "CThostFtdcRspInfoField",
        nRequestID: "int",
        bIsLast: "bool",
    ) -> "void":
        if pRspInfo is not None and pRspInfo.ErrorID != 0:
            self.finish(False, f"登录失败 ErrorID={pRspInfo.ErrorID}, ErrorMsg={pRspInfo.ErrorMsg}")
            return

        trading_day = pRspUserLogin.TradingDay if pRspUserLogin is not None else ""
        session_id = pRspUserLogin.SessionID if pRspUserLogin is not None else ""
        self.finish(True, f"登录成功 TradingDay={trading_day}, SessionID={session_id}")


def parse_args():
    parser = argparse.ArgumentParser(description="测试 CTP 交易前置连接与登录")
    parser.add_argument("--front", default=os.getenv("CTP_FRONT_ADDR", ""), help="交易前置地址")
    parser.add_argument("--broker", default=os.getenv("CTP_BROKER_ID", ""), help="经纪商代码")
    parser.add_argument("--user", default=os.getenv("CTP_USER_ID", ""), help="投资者账号")
    parser.add_argument("--password", default=os.getenv("CTP_PASSWORD", ""), help="账号密码")
    parser.add_argument("--timeout", type=int, default=15, help="超时时间（秒）")
    return parser.parse_args()


def validate_args(args):
    missing = []
    if not args.front:
        missing.append("front")
    if not args.broker:
        missing.append("broker")
    if not args.user:
        missing.append("user")
    if not args.password:
        missing.append("password")

    if missing:
        print(f"参数缺失: {', '.join(missing)}")
        print("请通过命令行参数或环境变量提供完整登录信息。")
        return False
    return True


def main():
    args = parse_args()
    if not validate_args(args):
        return 2

    trader_api = api.CThostFtdcTraderApi_CreateFtdcTraderApi()
    tester = TraderConnectionTester(trader_api, args.broker, args.user, args.password)

    trader_api.RegisterSpi(tester)
    trader_api.SubscribePrivateTopic(api.THOST_TERT_QUICK)
    trader_api.SubscribePublicTopic(api.THOST_TERT_QUICK)
    trader_api.RegisterFront(args.front)

    print(f"[CTP] 开始初始化，front={args.front}")
    trader_api.Init()

    start = time.time()
    while not tester.done.wait(timeout=0.2):
        if time.time() - start >= args.timeout:
            tester.finish(False, f"等待回调超时（>{args.timeout}s）")
            break

    if hasattr(trader_api, "Release"):
        trader_api.Release()

    if tester.success:
        print(f"[CTP] PASS: {tester.error_msg}")
        return 0

    print(f"[CTP] FAIL: {tester.error_msg}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
