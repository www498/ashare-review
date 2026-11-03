# -*- coding: utf-8 -*-
"""第二轮：测备用源（避开东财 push2 限流）"""
import time
import akshare as ak

def probe(name, fn):
    t0 = time.time()
    try:
        df = fn()
        print(f"[OK]   {name:30s} rows={len(df):<6d} {time.time()-t0:5.1f}s cols={list(df.columns)[:7]}")
    except Exception as e:
        print(f"[FAIL] {name:30s} {type(e).__name__}: {str(e)[:90]}")

# 历史K线备用源（回测必需）
probe("新浪日线 stock_zh_a_daily", lambda: ak.stock_zh_a_daily(symbol="sh600519", start_date="20260101", end_date="20261102", adjust="qfq"))
probe("腾讯日线 hist_tx", lambda: ak.stock_zh_a_hist_tx(symbol="sh600519", start_date="20260101", end_date="20261102", adjust="qfq"))
# 指数
probe("新浪指数 stock_zh_index_daily", lambda: ak.stock_zh_index_daily(symbol="sh000001"))
# 板块（备用：同花顺）
probe("同花顺行业板块", lambda: ak.stock_board_industry_summary_ths())
# 概念板块（东财，轻量）
probe("东财概念板块名称", lambda: ak.stock_board_concept_name_em())
# 涨跌家数统计
probe("涨跌停统计 stock_zt_pool_previous", lambda: ak.stock_zt_pool_previous_em(date="20261102"))
# 大盘资金流
probe("大盘资金流(东财)", lambda: ak.stock_market_fund_flow())
