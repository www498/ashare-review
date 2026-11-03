# -*- coding: utf-8 -*-
"""快速探测 akshare 关键接口可用性（复盘场景所需的 5 类数据）"""
import time, traceback
import akshare as ak

def probe(name, fn):
    t0 = time.time()
    try:
        df = fn()
        cost = time.time() - t0
        cols = list(df.columns)[:8]
        print(f"[OK]   {name:26s} rows={len(df):<6d} {cost:5.1f}s cols={cols}")
    except Exception as e:
        print(f"[FAIL] {name:26s} {type(e).__name__}: {str(e)[:120]}")

print("akshare", ak.__version__)

probe("全A实时行情 spot_em", lambda: ak.stock_zh_a_spot_em())
probe("行业板块行情", lambda: ak.stock_board_industry_name_em())
probe("个股资金流(600519)", lambda: ak.stock_individual_fund_flow(stock="600519", market="sh"))
probe("涨停股池(20261102)", lambda: ak.stock_zt_pool_em(date="20261102"))
probe("板块资金流排名", lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流"))
probe("龙虎榜详情", lambda: ak.stock_lhb_detail_em(start_date="20261027", end_date="20261102"))
probe("市场活跃度(赚钱效应)", lambda: ak.stock_market_activity_legu())
probe("千股千评", lambda: ak.stock_comment_em())
probe("历史K线(600519)", lambda: ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20260901", end_date="20261102", adjust="qfq"))
probe("北向资金汇总", lambda: ak.stock_hsgt_fund_flow_summary_em())
probe("财联社电报", lambda: ak.stock_info_global_cls())
