# -*- coding: utf-8 -*-
"""
持仓导入的本地网页界面。

为什么用内置 http.server 而不是 Flask：
这个项目的原则是零第三方依赖，能用标准库解决就不加包。一个单文件服务器足够。

流程：粘贴表格 → 自动识别列 → 预览可编辑 → 保存成 positions.csv → 可选立即重跑复盘

用法：python -m ashare.importer
      然后浏览器打开 http://127.0.0.1:8765
"""
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import positions as pos_mod
from .data import ROOT
from .web import CSS

PORT = 8765
# 每个账号独立的运行状态：多人同时在线时，A 的进度不能显示到 B 的面板上
STATE = {}


def _blank_state():
    return {"running": False, "ok": None, "tail": "", "target": None}


class _as_user:
    """临时把当前线程的账号上下文切到 uid，离开时恢复。
    watchlist 等模块通过 context 取路径，不切上下文会写到默认目录。"""

    def __init__(self, uid):
        self.uid = uid
        self.prev = None

    def __enter__(self):
        from . import context
        self.prev = context.current_uid()
        context.set_user(self.uid)
        return self

    def __exit__(self, *a):
        from . import context
        context.set_user(self.prev)
        return False

SAMPLE_TEXT = (
    "\u8bc1\u5238\u4ee3\u7801\t\u8bc1\u5238\u540d\u79f0\t\u6301\u4ed3\u6570\u91cf\t\u6210\u672c\u4ef7\t\u73b0\u4ef7\n"
    "600519\t\u8d35\u5dde\u8305\u53f0\t100\t1392.05\t1439.10\n"
    "300750\t\u5b81\u5fb7\u65f6\u4ee3\t200\t240.19\t245.00\n"
    "601318\t\u4e2d\u56fd\u5e73\u5b89\t1000\t48.30\t53.12\n"
    "688981\t\u4e2d\u82af\u56fd\u9645\t\t\t99.08\n"
)

PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>导入持仓</title><style>__CSS__
textarea{width:100%;height:150px;border:1px solid #dfe3e8;border-radius:8px;padding:10px;
  font-family:ui-monospace,Consolas,monospace;font-size:12.5px;resize:vertical;line-height:1.6}
textarea:focus{outline:none;border-color:#2f5fa8}
input[type=file]{font-size:13px;margin-bottom:10px}
button{border:none;border-radius:8px;padding:9px 18px;font-size:13.5px;cursor:pointer;
  background:#2f5fa8;color:#fff;font-weight:500}
button:hover{background:#27508f}
button:disabled{background:#c9ced6;cursor:not-allowed}
button.ghost{background:#eef2f8;color:#1a4d8f}
button.ghost:hover{background:#e2eaf6}
.row{margin-top:12px}
table.edit td{padding:4px 6px}
table.edit input{width:100%;border:1px solid #e6e8eb;border-radius:5px;padding:4px 6px;
  font-size:12.5px;font-variant-numeric:tabular-nums}
table.edit input:focus{outline:none;border-color:#2f5fa8}
.map{font-size:12.5px;color:#5f6368;background:#f6f8fa;border-radius:8px;padding:10px 12px;
  margin-bottom:12px;line-height:1.9}
.map b{color:#1a4d8f}
pre{background:#1f2328;color:#e6e8eb;border-radius:8px;padding:12px;font-size:11.5px;
  max-height:220px;overflow:auto;white-space:pre-wrap;margin-top:10px}
.err{color:#b3261e;font-size:13px;margin-top:8px}
.ok{color:#0b5c31}
</style></head><body><div class="wrap">
<div class="hd"><h1>导入持仓</h1>
<span class="sub">从东方财富 / 同花顺 / 券商导出，粘贴或选文件，自动识别列</span></div>

<div class="card"><h2>1. 粘贴表格或选择文件</h2>
<div class="hint">支持 Tab / 逗号 / 空格分隔；有表头会自动识别「代码 / 名称 / 持仓数量 / 成本价」，
列的顺序随意；没有表头则按「代码,名称,数量,成本」的位置解析</div>
<input type="file" id="f" accept=".csv,.txt,.tsv,.xls,.xlsx">
<textarea id="t" placeholder="把持仓表粘到这里，例如：&#10;证券代码&#9;证券名称&#9;持仓数量&#9;成本价&#10;600519&#9;贵州茅台&#9;100&#9;1392.05"></textarea>
<div class="row"><button id="btnParse">解析</button>
<button class="ghost" id="btnClear">清空</button>
<button class="ghost" id="btnSample">填入示例</button></div>
<div id="err1" class="err"></div></div>

<div class="card" id="step2" style="display:none"><h2>2. 确认数据（可直接修改）</h2>
<div class="hint">数量或成本留空的行会当作「只关注、不算盈亏」</div>
<div class="map" id="map"></div>
<div id="tblwrap"></div>
<div class="row"><button id="btnSave">保存为 positions.csv</button>
<span id="msg1" style="font-size:13px;margin-left:10px"></span></div></div>

<div class="card" id="step3" style="display:none"><h2>3. 完成</h2>
<div id="msg2" style="font-size:13.5px"></div>
<div class="row"><button id="btnRun">立即重新生成复盘</button>
<button class="ghost" id="btnOpen">打开看板</button></div>
<pre id="runlog" style="display:none"></pre></div>

<div class="ft">保存位置：项目根目录 positions.csv　·　与 watchlist.txt 自动合并，持仓数量以本文件为准</div>
</div>
<script>
var ROWS = [];
var $ = function(id){return document.getElementById(id);};

$('f').addEventListener('change', function(e){
  var file = e.target.files[0]; if(!file) return;
  $('err1').textContent = '';
  var r = new FileReader();
  // xlsx 为 ZIP 二进制，必须交后端解析；readAsText 只会得到 PK... 乱码
  if(/\\.(xlsx|xlsm|xls)$/i.test(file.name)){
    r.onload = function(){
      fetch('/upload', {method:'POST', headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({name:file.name, data:r.result})})
        .then(function(x){return x.json();})
        .then(function(d){
          if(d.error){ $('err1').textContent = d.error; return; }
          if(!d.rows || !d.rows.length){
            $('err1').textContent = '文件里没有识别到沪深京 A 股代码'; return;
          }
          ROWS = d.rows; render(d);
        })
        .catch(function(err){ $('err1').textContent = '上传失败：' + err; });
    };
    r.readAsDataURL(file);
  }else{
    r.onload = function(){ $('t').value = r.result; doParse(); };
    r.readAsText(file, 'UTF-8');
  }
});

var SAMPLE = __SAMPLE__;

$('btnSample').onclick = function(){ $('t').value = SAMPLE; doParse(); };

$('btnClear').onclick = function(){ $('t').value=''; $('step2').style.display='none';
  $('step3').style.display='none'; $('err1').textContent=''; };

$('btnParse').onclick = doParse;

function doParse(){
  var text = $('t').value.trim();
  $('err1').textContent = '';
  if(!text){ $('err1').textContent='先粘贴内容或选择文件'; return; }
  fetch('/parse', {method:'POST', headers:{'Content-Type':'application/json'},
                   body: JSON.stringify({text:text})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ $('err1').textContent = d.error; return; }
      if(!d.rows.length){ $('err1').textContent='没有识别到沪深京 A 股代码，检查一下表格内容'; return; }
      ROWS = d.rows; render(d);
    })
    .catch(function(e){ $('err1').textContent = '请求失败：' + e; });
}

function render(d){
  var m = d.meta || {};
  var html = '识别到 <b>' + d.rows.length + '</b> 只股票　·　' +
             (m.header ? '表头已识别' : '无表头，按位置解析');
  if(m.columns && Object.keys(m.columns).length){
    var names = {code:'代码', name:'名称', shares:'数量', cost:'成本价', price:'现价'};
    var parts = [];
    for(var k in m.columns){ parts.push(names[k] + '=第' + (m.columns[k]+1) + '列'); }
    html += '<br>列映射：' + parts.join('　');
  }
  var pc = d.rows.filter(function(x){return x.shares>0 && x.cost>0;}).length;
  html += '<br>其中 <b>' + pc + '</b> 只有完整持仓（数量+成本），其余按关注处理';
  $('map').innerHTML = html;

  var t = '<table class="edit" style="table-layout:fixed">' +
          '<colgroup><col style="width:82px"><col><col style="width:100px">' +
          '<col style="width:100px"><col style="width:92px"></colgroup>' +
          '<tr><th>代码</th><th>名称</th><th class="n">数量</th><th class="n">成本价</th>' +
          '<th class="n">市值</th></tr>';
  for(var i=0;i<d.rows.length;i++){
    var x = d.rows[i];
    t += '<tr><td>'+x.code+'</td>' +
         '<td><input data-i="'+i+'" data-k="name" value="'+(x.name||'')+'"></td>' +
         '<td><input data-i="'+i+'" data-k="shares" value="'+(x.shares||'')+'" ' +
         'style="text-align:right"></td>' +
         '<td><input data-i="'+i+'" data-k="cost" value="'+(x.cost||'')+'" ' +
         'style="text-align:right"></td>' +
         '<td class="n" id="mv'+i+'">'+(x.price && x.shares ? (x.shares*x.price).toLocaleString('zh-CN',{maximumFractionDigits:0}) : '—')+'</td></tr>';
  }
  t += '</table>';
  $('tblwrap').innerHTML = t;
  $('step2').style.display = '';
  $('step3').style.display = 'none';
  $('msg1').textContent = '';
}

document.addEventListener('input', function(e){
  var el = e.target;
  if(!el.dataset || el.dataset.k === undefined) return;
  var i = +el.dataset.i, k = el.dataset.k;
  ROWS[i][k] = (k==='name') ? el.value : (el.value === '' ? null : parseFloat(el.value));
  var mv = $('mv' + i);
  if(mv){
    var x = ROWS[i];
    mv.textContent = (x.price && x.shares)
      ? (x.shares * x.price).toLocaleString('zh-CN', {maximumFractionDigits:0}) : '—';
  }
});

$('btnSave').onclick = function(){
  var body = ROWS.map(function(x){
    return {code:x.code, name:x.name||'', shares:x.shares||null, cost:x.cost||null};
  });
  fetch('/save', {method:'POST', headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({rows:body})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){ $('msg1').innerHTML = '<span class="err">'+d.error+'</span>'; return; }
      $('msg1').innerHTML = '<span class="ok">已保存 '+d.saved+' 只到 positions.csv</span>';
      $('msg2').innerHTML = '已写入 <b>positions.csv</b>（'+d.saved+' 只，其中 '+d.withpos+
        ' 只有完整持仓）。<br>点下面的按钮重新生成今天的复盘，或双击 run_now.bat。';
      $('step3').style.display = '';
    })
    .catch(function(e){ $('msg1').innerHTML = '<span class="err">保存失败：'+e+'</span>'; });
};

$('btnRun').onclick = function(){
  $('btnRun').disabled = true; $('runlog').style.display=''; $('runlog').textContent = '正在生成…';
  fetch('/run', {method:'POST'}).then(function(){ poll(); });
};

function poll(){
  fetch('/status').then(function(r){return r.json();}).then(function(d){
    $('runlog').textContent = d.tail || '…';
    if(d.running){ setTimeout(poll, 1200); }
    else{
      $('btnRun').disabled = false;
      $('runlog').textContent = (d.ok ? '[完成]\\n' : '[失败]\\n') + (d.tail||'');
    }
  });
}

$('btnOpen').onclick = function(){ window.open('/open', '_blank'); };

if(new URLSearchParams(location.search).get('sample')){
  $('t').value = SAMPLE; doParse();
}
</script></body></html>"""


def _csv(rows):
    """写成带 BOM 的 CSV，Excel 双击打开不乱码"""
    lines = ["证券代码,证券名称,持仓数量,成本价"]
    for r in rows:
        sh = r.get("shares")
        ct = r.get("cost")
        lines.append(f"{r['code']},{r.get('name') or ''},"
                     f"{'' if sh is None else sh},{'' if ct is None else ct}")
    return "\n".join(lines)


def _cookie_token(handler):
    """从 Cookie 取会话 token。"""
    raw = handler.headers.get("Cookie") or ""
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "sid":
            return v
    return None


def _current_user(handler):
    from . import auth
    return auth.whoami(_cookie_token(handler))


def _user_reports(uid):
    from . import auth
    return auth.paths(uid)["reports"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_with_cookie(self, token, obj):
        """登录成功时下发会话 Cookie。
        HttpOnly 防止 JS 读取；SameSite=Lax 防 CSRF；
        未设 Secure 是因为本地服务无 HTTPS，设了浏览器反而不会存。"""
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Set-Cookie",
            f"sid={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={7 * 86400}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        user = _current_user(self)

        # 登录页与静态登录资源无需鉴权
        if path in ("/login", "/register"):
            from .authpage import LOGIN_PAGE
            self._send(200, LOGIN_PAGE.replace("__CSS__", CSS),
                       "text/html; charset=utf-8")
            return
        if path == "/me":
            self._send(200, json.dumps(
                {"user": user, "has_users": __import__(
                    "ashare.auth", fromlist=["auth"]).count_users() > 0},
                ensure_ascii=False))
            return

        # 其余全部需要登录
        if not user:
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return

        uid = user["uid"]
        if path in ("/", "/index.html"):
            idx = os.path.join(_user_reports(uid), "index.html")
            if os.path.exists(idx):
                self.send_response(302)
                self.send_header("Location", "/reports/index.html")
                self.end_headers()
                return
            html = (PAGE.replace("__CSS__", CSS)
                    .replace("__SAMPLE__", json.dumps(SAMPLE_TEXT, ensure_ascii=False)))
            self._send(200, html, "text/html; charset=utf-8")
        elif path == "/import":
            html = (PAGE.replace("__CSS__", CSS)
                    .replace("__SAMPLE__", json.dumps(SAMPLE_TEXT, ensure_ascii=False)))
            self._send(200, html, "text/html; charset=utf-8")
        elif path == "/status":
            self._send(200, json.dumps(STATE.get(uid, _blank_state()),
                                       ensure_ascii=False))
        elif path == "/sample":
            self._send(200, json.dumps({"text": SAMPLE_TEXT}, ensure_ascii=False))
        elif path == "/list":
            self._send(200, json.dumps({"items": _report_list(uid)}, ensure_ascii=False))
        elif path == "/watchlist":
            self._send(200, json.dumps({"items": _watch_items(uid)}, ensure_ascii=False))
        elif path == "/open":
            idx = os.path.join(_user_reports(uid), "index.html")
            if os.path.exists(idx):
                self.send_response(302)
                self.send_header("Location", "/reports/index.html")
                self.end_headers()
            else:
                self._send(404, "还没有报告，先跑一次复盘")
        elif path.startswith("/reports/"):
            name = os.path.basename(path[len("/reports/"):])
            fp = os.path.join(_user_reports(uid), name)
            if os.path.exists(fp):
                ctype = ("text/html; charset=utf-8" if name.endswith(".html")
                         else "text/plain; charset=utf-8" if name.endswith(".md")
                         else "application/octet-stream")
                body = open(fp, encoding="utf-8").read()
                if name.endswith(".html"):
                    try:
                        from .panel_js import inject
                        body = inject(body, username=user["username"])
                    except Exception:
                        pass
                self._send(200, body, ctype)
            else:
                self._send(404, "not found")
        else:
            self._send(404, "not found")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            payload = {}

        path = urlparse(self.path).path
        from . import auth

        # ---- 认证接口（无需登录）----
        if path == "/api/register":
            ok, msg, uid = auth.register(payload.get("username", ""),
                                         payload.get("password", ""))
            if not ok:
                self._send(200, json.dumps({"error": msg}, ensure_ascii=False))
                return
            ok2, msg2, token, user = auth.login(payload.get("username", ""),
                                                payload.get("password", ""))
            self._send_with_cookie(token, {"ok": True, "msg": msg, "user": user})
            return

        if path == "/api/login":
            ok, msg, token, user = auth.login(payload.get("username", ""),
                                              payload.get("password", ""))
            if not ok:
                self._send(200, json.dumps({"error": msg}, ensure_ascii=False))
                return
            self._send_with_cookie(token, {"ok": True, "msg": msg, "user": user})
            return

        if path == "/api/logout":
            auth.logout(_cookie_token(self))
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie",
                             "sid=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0")
            body = json.dumps({"ok": True}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # ---- 以下全部需要登录 ----
        user = _current_user(self)
        if not user:
            self._send(401, json.dumps({"error": "登录已失效，请重新登录",
                                        "need_login": True}, ensure_ascii=False))
            return
        uid = user["uid"]

        if path == "/api/password":
            ok, msg = auth.change_password(user["username"],
                                           payload.get("old", ""),
                                           payload.get("new", ""))
            self._send(200, json.dumps({"ok": ok, "msg" if ok else "error": msg},
                                       ensure_ascii=False))

        elif path == "/parse":
            text = payload.get("text", "")
            try:
                watch, pos, meta = pos_mod.parse_text(text)
            except Exception as e:
                self._send(200, json.dumps({"error": f"解析失败：{e}"}, ensure_ascii=False))
                return
            prices = (meta or {}).get("prices") or {}
            rows = []
            for code, name in watch.items():
                p = pos.get(code) or {}
                rows.append({"code": code, "name": "" if name == code else name,
                             "shares": p.get("shares"), "cost": p.get("cost"),
                             "price": prices.get(code)})
            self._send(200, json.dumps({"rows": rows, "meta": meta}, ensure_ascii=False))

        elif path == "/upload":
            # xlsx 是 ZIP 二进制，浏览器端 readAsText 只会得到 PK... 乱码。
            # 必须把原始字节交给后端用 openpyxl/pandas 解析。
            import base64
            b64 = payload.get("data") or ""
            fname = payload.get("name") or "upload.xlsx"
            try:
                raw = base64.b64decode(b64.split(",")[-1])
            except Exception as e:
                self._send(200, json.dumps({"error": f"文件内容无法解码：{e}"},
                                           ensure_ascii=False))
                return
            try:
                text = _bytes_to_text(raw, fname)
            except Exception as e:
                self._send(200, json.dumps({"error": str(e)}, ensure_ascii=False))
                return
            try:
                watch, pos, meta = pos_mod.parse_text(text)
            except Exception as e:
                self._send(200, json.dumps({"error": f"解析失败：{e}"}, ensure_ascii=False))
                return
            prices = (meta or {}).get("prices") or {}
            rows = []
            for code, name in watch.items():
                p = pos.get(code) or {}
                rows.append({"code": code, "name": "" if name == code else name,
                             "shares": p.get("shares"), "cost": p.get("cost"),
                             "price": prices.get(code)})
            self._send(200, json.dumps({"rows": rows, "meta": meta}, ensure_ascii=False))

        elif path == "/watchlist":
            try:
                from . import watchlist as wl_mod
                act = payload.get("action")
                codes = payload.get("codes") or []
                if isinstance(codes, str):
                    # 直接抓「6位代码 + 可选的紧跟名称」，不做分隔符切分。
                    # 按逗号整串切会把「002594,比亚迪」拆成两项，名称成为无法识别的孤立词。
                    codes = [m.group(0).strip(" ,，\t")
                             for m in re.finditer(
                                 r"\d{6}(?:\s*[,，]\s*[^\s,，;；\d][^\s,，;；]*)?", codes)]
                if act == "add":
                    with _as_user(uid):
                        added, dup, bad = wl_mod.add_codes(codes)
                    msg = []
                    if added:
                        msg.append(f"已添加 {len(added)} 只")
                    if dup:
                        msg.append(f"{len(dup)} 只已存在")
                    if bad:
                        msg.append(f"{len(bad)} 条无法识别")
                    self._send(200, json.dumps(
                        {"ok": True, "msg": "，".join(msg) or "没有变化",
                         "added": added, "dup": dup, "bad": bad,
                         "items": _watch_items(uid)}, ensure_ascii=False))
                elif act == "remove":
                    with _as_user(uid):
                        removed, nf = wl_mod.remove_codes(codes)
                    msg = f"已删除 {len(removed)} 只" if removed else "没有匹配的标的"
                    if nf:
                        msg += f"，{len(nf)} 只未找到"
                    self._send(200, json.dumps(
                        {"ok": True, "msg": msg, "removed": removed,
                         "items": _watch_items(uid)}, ensure_ascii=False))
                else:
                    self._send(200, json.dumps({"error": "未知操作"}, ensure_ascii=False))
            except Exception as e:
                self._send(200, json.dumps({"error": f"操作失败：{e}"}, ensure_ascii=False))

        elif path == "/save":
            rows = payload.get("rows") or []
            if not rows:
                self._send(200, json.dumps({"error": "没有可保存的数据"}, ensure_ascii=False))
                return
            try:
                fp = os.path.join(auth.paths(uid)["root"], "positions.csv")
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, "w", encoding="utf-8-sig") as f:
                    f.write(_csv(rows))
                withpos = sum(1 for r in rows if r.get("shares") and r.get("cost"))
                self._send(200, json.dumps({"saved": len(rows), "withpos": withpos},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(200, json.dumps({"error": f"写入失败：{e}"}, ensure_ascii=False))

        elif path == "/run":
            st = STATE.get(uid) or _blank_state()
            if not st["running"]:
                session = payload.get("session")
                session = session if session in ("am", "pm") else "pm"
                offline = bool(payload.get("offline"))
                threading.Thread(target=_run_review, args=(session, offline, uid),
                                 daemon=True).start()
            self._send(200, json.dumps({"started": True}))

        else:
            self._send(404, "not found")


def _watch_items(uid=None):
    """当前账号的自选股清单，带持仓标记与实时价，供面板展示。"""
    try:
        from . import data as data_mod
        from . import watchlist as wl_mod
        with _as_user(uid):
            watch, pos, _ = wl_mod.load()
        quotes = {}
        try:
            quotes = data_mod.fetch_quotes(list(watch.keys()))
        except Exception:
            pass
        out = []
        for code, name in watch.items():
            q = quotes.get(code) or {}
            p = pos.get(code) or {}
            out.append({
                "code": code,
                "name": q.get("name") or (name if name != code else ""),
                "price": q.get("price"), "pct": q.get("pct"),
                "shares": p.get("shares"), "cost": p.get("cost"),
                "held": bool(p.get("shares")),
            })
        out.sort(key=lambda x: (not x["held"], x["code"]))
        return out
    except Exception:
        return []


def _drop_positions(codes, uid=None):
    """从该账号的 positions.csv 删除指定代码。
    删自选股时同步清理，否则会被重新合并进来。"""
    if not codes:
        return
    import os as _os

    from . import auth
    fp = _os.path.join(auth.paths(uid)["root"], "positions.csv")
    if not _os.path.exists(fp):
        return
    want = set(codes)
    with open(fp, encoding="utf-8-sig", errors="ignore") as f:
        lines = f.readlines()
    kept = [ln for ln in lines
            if not any(ln.strip().startswith(c) or f",{c}," in ln for c in want)]
    if len(kept) != len(lines):
        with open(fp, "w", encoding="utf-8-sig") as f:
            f.writelines(kept)


def _bytes_to_text(raw, filename=""):
    """把上传的原始字节转成 CSV 文本，供 positions.parse_text 解析。

    xlsx/xlsm 走 pandas（ZIP 二进制，不能按文本读）；
    CSV/TXT 依次尝试常见编码 —— 券商导出多为 GBK，按 UTF-8 读会抛异常或乱码。
    """
    import io
    import os as _os

    ext = _os.path.splitext(filename)[1].lower()
    if raw[:2] == b"PK" or ext in (".xlsx", ".xlsm"):
        import pandas as pd
        df = pd.read_excel(io.BytesIO(raw), dtype=str)
        return df.to_csv(index=False)
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or ext == ".xls":
        raise ValueError("这是老版 .xls 格式，请在 Excel 里另存为 .xlsx 或 .csv 后再导入。")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _report_list(uid=None):
    """已生成的报表，供页头日期下拉切换用。看板优先、按日期倒序。"""
    rd = _user_reports(uid)
    if not os.path.isdir(rd):
        return []
    items = []
    if os.path.exists(os.path.join(rd, "history.html")):
        items.append({"label": "市场温度历史趋势", "tag": "趋势",
                      "url": "/reports/history.html"})
    names = sorted((f for f in os.listdir(rd) if f.startswith("dashboard_")
                    and f.endswith(".html")), reverse=True)
    for f in names:
        stem = f[len("dashboard_"):-len(".html")]        # 20261102_pm
        d, _, s = stem.partition("_")
        label = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        items.append({"label": f"{label} {'收盘' if s == 'pm' else '午盘'}看板",
                      "tag": "看板", "url": f"/reports/{f}"})
    for f in sorted((f for f in os.listdir(rd) if f.endswith(".md")), reverse=True):
        stem = f[:-3]
        d, _, s = stem.partition("_")
        if len(d) != 8 or not d.isdigit():
            continue
        label = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        items.append({"label": f"{label} {'收盘' if s == 'pm' else '午盘'}报告（Markdown）",
                      "tag": "文本", "url": f"/reports/{f}"})
    return items


def _run_review(session="pm", offline=False, uid=None):
    STATE[uid] = {"running": True, "ok": None, "tail": "正在取数…", "target": None}
    cmd = [sys.executable, os.path.join(ROOT, "run_review.py"), "--session", session]
    if session == "pm":
        cmd.append("--forecast")
    if offline:
        cmd.append("--offline")
    if uid:
        cmd += ["--user", uid]          # 子进程里按账号读写，天然隔离
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="ignore", timeout=600)
        tail = (p.stdout or "")[-1500:]
        ok = p.returncode == 0
        target = None
        if ok:
            import re as _re
            m = _re.findall(r"dashboard_(\d{8}_(?:am|pm))\.html", p.stdout or "")
            if m:
                target = f"/reports/dashboard_{m[-1]}.html"
        STATE[uid] = {"running": False, "ok": ok, "target": target,
                      "tail": tail if tail.strip() else (p.stderr or "")[-800:]}
    except Exception as e:
        STATE[uid] = {"running": False, "ok": False, "target": None,
                      "tail": f"执行失败：{e}"}


def main():
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"端口 {PORT} 被占用，可能已经开着一个导入页面了。")
        print(f"直接打开 http://127.0.0.1:{PORT}")
        return
    url = f"http://127.0.0.1:{PORT}"
    print(f"复盘工作台已启动：{url}")
    print("登录后看板右上角可切换日期、生成即时复盘；持仓卡片右侧可导入持仓。")
    print("按 Ctrl+C 停止")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        srv.shutdown()


if __name__ == "__main__":
    main()
