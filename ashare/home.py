# -*- coding: utf-8 -*-
"""主页面：先看「我这个人」，再按天翻我的操作。

为什么需要这一页
----------------
看板是按天切片的，一天一个 HTML。用户真正要回答的问题却是连续的：
「我最近做得怎么样」「上周三那笔到底怎么想的」「今天的复盘生成了没」。
没有一个固定的落脚点，每次都得先找到某一天的看板才能点生成按钮。

所以主页把三件事放在一屏里：
- 交易行为画像（不随日期变，是这个人的底稿）
- 每天两次复盘，按时间倒序列出来，有就点进去，没有就当场生成
- 生成入口本身（早盘 / 全天 / 即时），不再藏在内页页头

数据全部读自 users/<uid>/ 下的快照与报告，不额外落库。
"""
import glob
import os

from . import context, data as data_mod, web


HOME_CSS = """
.hdact{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.usr{display:inline-flex;align-items:center;gap:6px;padding:4px 10px 4px 5px;
  border-radius:999px;background:#f2f5f9;font-size:12.5px;color:#3c4043}
.usr i{width:19px;height:19px;border-radius:50%;background:#2f5fa8;color:#fff;
  font-style:normal;font-size:11px;font-weight:600;display:flex;align-items:center;
  justify-content:center}
.btn{border:1px solid #dfe3e8;background:#fff;border-radius:8px;padding:6px 14px;
  font-size:12.5px;color:#1a4d8f;cursor:pointer;font-family:inherit;font-weight:500;
  white-space:nowrap;transition:background .15s,border-color .15s}
.btn:hover{border-color:#2f5fa8;background:#f7f9fc}
.btn.pri{background:#2f5fa8;color:#fff;border-color:#2f5fa8}
.btn.pri:hover{background:#27508f}
.btn:disabled{background:#e9edf3;color:#9aa3b0;border-color:#e2e8f0;cursor:not-allowed}
.ghost{background:transparent;border:none;color:#8a8f98;font-size:12.5px;
  cursor:pointer;font-family:inherit;text-decoration:none}
.ghost:hover{color:#2f5fa8}
.genbar{display:none;align-items:center;gap:10px;margin:14px 0 0;padding:10px 14px;
  border-radius:9px;background:#eef3fb;border:1px solid #dbe6f5;font-size:12.5px;color:#24405f}
.genbar.on{display:flex}
.genbar .dot{width:8px;height:8px;border-radius:50%;background:#2f5fa8;
  animation:gp 1.1s ease-in-out infinite}
@keyframes gp{0%,100%{opacity:.25}50%{opacity:1}}
.genbar code{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;
  color:#6b7686;background:#fff;padding:1px 6px;border-radius:4px}
.days{margin-top:2px}
.drow{display:flex;align-items:center;gap:10px;padding:11px 2px;
  border-bottom:1px solid #f2f4f7;flex-wrap:wrap}
.drow:last-child{border-bottom:none}
.dday{width:104px;font-variant-numeric:tabular-nums;font-size:13px;color:#3c4043;font-weight:500}
.dday small{display:block;font-size:11px;color:#9aa3b0;font-weight:400;letter-spacing:0}
.dlink{flex:0 0 auto;font-size:12px;padding:4px 12px;border-radius:7px;text-decoration:none;
  border:1px solid #dfe3e8;color:#1a4d8f;background:#fff;font-weight:500}
.dlink:hover{border-color:#2f5fa8;background:#f7f9fc}
.dlink.none{color:#b6bcc5;background:#fafbfc;border-color:#eef0f3;pointer-events:none}
.dmeta{font-size:11.5px;color:#9aa3b0;margin-left:auto}
.dempty{padding:22px 0;text-align:center;font-size:13px;color:#8a8f98}
.stmt{display:flex;align-items:center;gap:10px;font-size:12.5px;color:#5f6b7a;
  margin:-6px 0 4px;flex-wrap:wrap}
.stmt b{color:#243043}
.stmt .ok{color:#0b7a45}
.stmt .no{color:#b4530a}
@media(max-width:700px){.hdact{margin-left:0;width:100%}.dday{width:100%}}
"""


def _with_user(uid, fn):
    """在指定账号上下文里执行。主页要读 users/<uid>/，不切上下文会读到默认目录。"""
    prev = context.current_uid()
    context.set_user(uid)
    try:
        return fn()
    finally:
        context.set_user(prev)


def _latest_ctx():
    """最新一份快照。主页的画像、账户摘要都从它来，不重新取数。"""
    try:
        files = sorted(glob.glob(os.path.join(context.snapshots_dir(), "*.json")),
                       reverse=True)
        for fp in files[:6]:
            ctx = data_mod.load_snapshot(os.path.basename(fp)[:-5])
            if ctx:
                return ctx
    except Exception:
        pass
    return None


def _day_rows():
    """每天的复盘文件 → [{date, am, pm, md}]，按日期倒序。

    同一天可能有早盘和全天两份，也可能只跑了一次。分开列出来，
    因为用户经常只是想补看早盘那份。
    """
    rd = context.reports_dir()
    if not os.path.isdir(rd):
        return []
    days = {}
    for f in os.listdir(rd):
        if f.startswith("dashboard_") and f.endswith(".html"):
            stem = f[len("dashboard_"):-len(".html")]     # 20261104_pm
            d, _, s = stem.partition("_")
            if len(d) == 8 and d.isdigit() and s in ("am", "pm"):
                days.setdefault(d, {})[s] = f
        elif f.endswith(".md"):
            stem = f[:-3]
            d, _, s = stem.partition("_")
            if len(d) == 8 and d.isdigit() and s in ("am", "pm"):
                days.setdefault(d, {}).setdefault("md_" + s, True)
    out = []
    for d in sorted(days, reverse=True):
        row = days[d]
        out.append({"date": d, "am": row.get("am"), "pm": row.get("pm"),
                    "md_am": row.get("md_am"), "md_pm": row.get("md_pm")})
    return out


def _badge(t):
    if t["total"] >= 62:
        return "b-hot"
    return "b-cool" if t["total"] < 45 else "b-mid"


def render(username="", uid=None):
    ctx = _with_user(uid, _latest_ctx) if uid else _latest_ctx()
    rows = _with_user(uid, _day_rows) if uid else _day_rows()

    h = []
    h.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
    h.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    h.append('<title>复盘台 · 我的交易复盘</title>')
    h.append(f"<style>{web.CSS}{HOME_CSS}</style></head><body><div class='wrap'>")

    # ---- 页头 ----
    h.append('<div class="hd">')
    h.append('<h1>复盘台</h1>')
    if ctx:
        idx = (ctx.get("indices") or [[None, None]])[0][1]
        sub = f'{ctx.get("date", "")}'
        if idx:
            sub += f'　上证 {idx["price"]:,.2f}　<span class="{web._c(idx["pct"])}">' \
                   f'{idx["pct"]:+.2f}%</span>'
        t = ctx.get("temperature") or {}
        if t:
            sub += f'　<span class="badge {_badge(t)}">{t["band"]} {t["total"]:.1f}</span>'
        h.append(f'<span class="sub">{sub}</span>')
    else:
        h.append('<span class="sub">还没有任何复盘记录</span>')
    h.append('<span class="hdact">')
    if username:
        h.append(f'<span class="usr"><i>{username[:1]}</i>{username}</span>')
    h.append('<a class="btn" href="/import">导入交割单</a>')
    h.append('<button class="btn" id="g-am" type="button">早盘复盘</button>')
    h.append('<button class="btn pri" id="g-pm" type="button">全天复盘</button>')
    h.append('<button class="btn" id="g-now" type="button">即时复盘</button>')
    if username:
        h.append('<button class="ghost" id="logout" type="button">退出</button>')
    h.append("</span></div>")

    h.append('<div class="genbar" id="genbar"><span class="dot"></span>'
             '<span id="gentext">正在启动…</span></div>')

    # ---- 今日摘要 ----
    # 只放「今天」的东西：累计的、结构性的指标在画像卡片里已经有了，
    # 这里再抄一遍会让主页变成两张重复的表。
    if ctx:
        port = ctx.get("portfolio") or {}
        jr = ctx.get("journal") or {}
        kp = []
        if port.get("total_mv"):
            kp.append(("持仓市值", f'{port["total_mv"]:,.0f}', "元", ""))
        if port.get("total_today") is not None:
            v = port["total_today"]
            kp.append(("今日盈亏", f"{v:+,.0f}", "元", web._c(v)))
        if port.get("total_pnl") is not None:
            v = port["total_pnl"]
            kp.append(("持仓浮盈", f"{v:+,.0f}", "元", web._c(v)))
        sm = jr.get("summary") or {}
        if sm.get("n"):
            kp.append(("今日成交", f'{sm["n"]}', f'买 {sm.get("buys", 0)} 卖 {sm.get("sells", 0)}', ""))
        if port.get("rows"):
            kp.append(("持仓只数", f'{len(port["rows"])}', "只", ""))
        if kp:
            h.append('<div class="kpis">')
            for lab, val, unit, cls in kp:
                h.append(f'<div class="kpi"><div class="lab">{lab}</div>'
                         f'<div class="val {cls}">{val}<small>{unit}</small></div></div>')
            h.append("</div>")

    # ---- 交易行为画像：这一页的主角，位置固定，不随后续内容挪动 ----
    if ctx:
        web._sec_profile(h, ctx, compact=True)
    else:
        h.append('<div class="card"><h2>交易行为画像</h2>')
        h.append('<div class="hint">还没有数据。行为画像必须从<b>成交流水</b>算 '
                 '——哪天买了什么、卖了多少，只有持仓表算不出来。</div>')
        h.append('<div style="margin-top:12px">'
                 '<a class="btn pri" href="/import">导入交割单</a></div></div>')

    # ---- 每日复盘 ----
    h.append('<div class="card"><h2>每日交易复盘</h2>')
    h.append('<div class="hint">每跑一次就留一份，按日期倒序。'
             '早盘看重盘中情绪，全天看收盘结论，两份互不覆盖。</div>')
    if rows:
        h.append('<div class="days">')
        for i, r in enumerate(rows):
            d = r["date"]
            label = f'{d[:4]}-{d[4:6]}-{d[6:8]}'
            extra = "今天" if d == _today() else (
                "昨天" if d == _yesterday() else "")
            sub = f"<small>{extra or label[:4]}</small>" if extra else ""
            h.append(f'<div class="drow"><div class="dday">{label[5:]}{sub}</div>')
            for s, nm in (("am", "早盘"), ("pm", "全天")):
                f = r.get(s)
                if f:
                    h.append(f'<a class="dlink" href="/reports/{f}">{nm}复盘</a>')
                else:
                    h.append(f'<span class="dlink none">{nm}未生成</span>')
            md = [x for x in (r.get("md_am"), r.get("md_pm")) if x]
            h.append(f'<span class="dmeta">{"有 Markdown 报告" if md else ""}</span>')
            h.append("</div>")
        h.append("</div>")
    else:
        h.append('<div class="dempty">还没有复盘记录。先导入交割单，'
                 '再点右上角「全天复盘」跑第一次。</div>')
    h.append("</div>")

    h.append('<div style="text-align:center;margin:22px 0 0">'
             '<a class="ghost" href="/reports/index.html">查看全部报告 →</a></div>')

    h.append(f"<script>{_JS}</script>")
    h.append("</div></body></html>")
    return "".join(h)


def _today():
    import datetime as dt
    return dt.date.today().strftime("%Y%m%d")


def _yesterday():
    import datetime as dt
    return (dt.date.today() - dt.timedelta(days=1)).strftime("%Y%m%d")


_JS = r"""
function $(id){ return document.getElementById(id); }
var busy = false, t0 = 0, cur = '';

function setBusy(on, text){
  busy = on;
  ['g-am','g-pm','g-now'].forEach(function(k){ $(k).disabled = on; });
  var bar = $('genbar');
  bar.classList.toggle('on', on);
  if(text) $('gentext').textContent = text;
}

function start(session, label){
  if(busy) return;
  t0 = Date.now(); cur = session;
  setBusy(true, label + ' 正在启动…');
  fetch('/run', {method:'POST', headers:{'Content-Type':'application/json'},
                 body: JSON.stringify({session: session})})
    .then(function(){ poll(); })
    .catch(function(){ setBusy(false); alert('启动失败，检查工作台是否还在运行'); });
}

// 与看板内的按钮同一套逻辑：报阶段、报秒数、网络抖动不中断轮询
function poll(){
  var sec = Math.round((Date.now() - t0) / 1000);
  fetch('/status').then(function(r){ return r.json(); }).then(function(d){
    if(d.running){
      if(sec > 780){
        setBusy(false);
        alert('已等待 ' + Math.round(sec/60) + ' 分钟仍未完成。\n\n' + (d.tail || '').slice(-300));
        return;
      }
      var step = d.step ? ' \u00b7 ' + d.step : '';
      $('gentext').textContent = (cur === 'am' ? '早盘复盘' : '全天复盘')
        + ' 进行中 \u00b7 ' + sec + 's' + step;
      setTimeout(poll, 1200);
      return;
    }
    if(d.ok){
      $('gentext').textContent = '完成，正在刷新…';
      setTimeout(function(){ location.reload(); }, 600);
      return;
    }
    setBusy(false);
    alert('生成失败。\n\n' + ((d.tail || '').slice(-500) || '子进程没有返回输出'));
  }).catch(function(){ setTimeout(poll, 2500); });
}

$('g-am').onclick = function(){ start('am', '早盘复盘'); };
$('g-pm').onclick = function(){ start('pm', '全天复盘'); };
$('g-now').onclick = function(){
  var n = new Date(), m = n.getHours() * 60 + n.getMinutes();
  start(m < 13 * 60 ? 'am' : 'pm', m < 13 * 60 ? '早盘复盘' : '全天复盘');
};
var lo = $('logout');
if(lo) lo.onclick = function(){
  fetch('/api/logout', {method:'POST'}).then(function(){ location.href = '/login'; });
};
"""
