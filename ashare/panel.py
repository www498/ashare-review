# -*- coding: utf-8 -*-
"""
看板内联操作层。

设计原则：**操作贴着它作用的对象**，不再用一个悬浮球把四件事塞进同一个弹窗。
- 导入持仓   → 「持仓」卡片标题右侧
- 增删自选股 → 「自选股」卡片标题右侧 + 每行删除
- 生成即时复盘 / 切换日期 / 账号与退出 → 页头右侧

实现方式：把一段自包含的 CSS + HTML + JS 注入 importer 托管的 HTML 页面。
看板本身仍是单文件零依赖的静态页——直接双击打开时不含这段代码，
因为导入与重跑必须有后端；此时页面上什么都不显示，而不是留一堆点不动的按钮。

命名统一 wbp- 前缀，避免和 web.py 既有的 tr.exp 展开脚本冲突。
"""

PANEL_CSS = """
/* ---- 页头右侧操作区 ---- */
.wbp-hdact{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.wbp-a{border:none;border-radius:8px;padding:6px 13px;font-size:12.5px;cursor:pointer;
  background:#2f5fa8;color:#fff;font-family:inherit;font-weight:500;white-space:nowrap;
  transition:background .15s}
.wbp-a:hover{background:#27508f}
.wbp-a:disabled{background:#c9ced6;cursor:not-allowed}
.wbp-a.ghost{background:#eef2f8;color:#1a4d8f}
.wbp-a.ghost:hover{background:#e2eaf6}
#wbp-date{border:1px solid #dfe3e8;border-radius:8px;padding:5px 8px;font-size:12.5px;
  font-family:inherit;color:#3c4043;background:#fff;cursor:pointer;max-width:190px}
#wbp-date:focus{outline:none;border-color:#2f5fa8}
.wbp-user{display:inline-flex;align-items:center;gap:6px;padding:4px 10px 4px 6px;
  border-radius:999px;background:#f2f5f9;font-size:12.5px;color:#3c4043}
.wbp-user i{width:19px;height:19px;border-radius:50%;background:#2f5fa8;color:#fff;
  font-style:normal;font-size:11px;font-weight:600;display:flex;align-items:center;
  justify-content:center}

/* ---- 卡片标题里的内联按钮 ---- */
.wbp-slot{display:inline-flex;gap:6px;align-items:center;margin-left:10px;vertical-align:middle}
.wbp-btnx{border:1px solid #dfe3e8;background:#fff;border-radius:7px;padding:3px 10px;
  font-size:12px;color:#1a4d8f;cursor:pointer;font-family:inherit;font-weight:500}
.wbp-btnx:hover{border-color:#2f5fa8;background:#f7f9fc}
.wbp-btnx.danger:hover{border-color:#b3261e;color:#b3261e;background:#fdf4f3}

/* ---- 自选股：行内删除 + 添加条 ---- */
.wbp-del{border:none;background:none;color:#aab2be;cursor:pointer;font-size:15px;
  line-height:1;padding:1px 6px;margin-left:6px;border-radius:5px;font-family:inherit;
  vertical-align:middle}
.wbp-del:hover{background:#fdecea;color:#b3261e}
tr.exp td:last-child{white-space:nowrap}
.wbp-addbar{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.wbp-addbar input{flex:1;min-width:200px;border:1px solid #dfe3e8;border-radius:8px;
  padding:7px 10px;font-size:12.5px;font-family:inherit}
.wbp-addbar input:focus{outline:none;border-color:#2f5fa8}
.wbp-tip{font-size:12px;color:#8a8f98}

/* ---- 弹窗（只用于导入持仓） ---- */
#wbp-mask{position:fixed;inset:0;z-index:9999;background:rgba(24,28,34,.55);
  display:none;align-items:center;justify-content:center;padding:24px}
#wbp-mask.on{display:flex}
#wbp-dlg{background:#fff;border-radius:14px;width:100%;max-width:820px;
  max-height:calc(100vh - 48px);overflow:auto;box-shadow:0 20px 60px rgba(0,0,0,.28)}
#wbp-hd{display:flex;align-items:center;justify-content:space-between;
  padding:16px 20px 12px;border-bottom:1px solid #eef0f3;position:sticky;top:0;background:#fff;
  border-radius:14px 14px 0 0;z-index:1}
#wbp-hd h3{margin:0;font-size:15.5px;color:#1f2328;font-weight:600}
#wbp-x{background:none;border:none;font-size:22px;line-height:1;color:#8a9099;
  cursor:pointer;padding:0 4px;font-family:inherit}
#wbp-x:hover{color:#1f2328}
.wbp-pane{padding:16px 20px 20px}
.wbp-hint{font-size:12.5px;color:#5f6368;line-height:1.8;margin-bottom:12px}
#wbp-ta{width:100%;height:124px;border:1px solid #dfe3e8;border-radius:8px;padding:10px;
  font-family:ui-monospace,Consolas,monospace;font-size:12px;resize:vertical;line-height:1.6;
  box-sizing:border-box}
#wbp-ta:focus{outline:none;border-color:#2f5fa8}
.wbp-btn{border:none;border-radius:8px;padding:8px 16px;font-size:13px;cursor:pointer;
  background:#2f5fa8;color:#fff;font-family:inherit;font-weight:500}
.wbp-btn:hover{background:#27508f}
.wbp-btn:disabled{background:#c9ced6;cursor:not-allowed}
.wbp-btn.g{background:#eef2f8;color:#1a4d8f}
.wbp-btn.g:hover{background:#e2eaf6}
.wbp-row{margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.wbp-map{font-size:12.5px;color:#5f6368;background:#f6f8fa;border-radius:8px;
  padding:9px 12px;margin-bottom:10px;line-height:1.9}
.wbp-map b{color:#1a4d8f}
#wbp-tbl{max-height:260px;overflow:auto}
#wbp-tbl table{width:100%;border-collapse:collapse;font-size:12.5px}
#wbp-tbl th{text-align:left;padding:6px;border-bottom:1px solid #e6e8eb;color:#5f6368;
  font-weight:500;position:sticky;top:0;background:#fff}
#wbp-tbl td{padding:4px 6px;border-bottom:1px solid #f2f4f6}
#wbp-tbl th.n,#wbp-tbl td.n{text-align:right;font-variant-numeric:tabular-nums}
#wbp-tbl input{width:100%;border:1px solid #e6e8eb;border-radius:5px;padding:4px 6px;
  font-size:12.5px;font-family:inherit;box-sizing:border-box}
#wbp-tbl input:focus{outline:none;border-color:#2f5fa8}
.wbp-err{color:#b3261e;font-size:12.5px;margin-top:8px}
.wbp-ok{color:#0b5c31;font-size:12.5px}
#wbp-log{background:#1f2328;color:#e6e8eb;border-radius:8px;padding:10px 12px;
  font-size:11.5px;line-height:1.7;max-height:180px;overflow:auto;white-space:pre-wrap;
  margin-top:12px;display:none;font-family:ui-monospace,Consolas,monospace}
@media(max-width:760px){
  .wbp-hdact{width:100%;margin-left:0;margin-top:8px}
  #wbp-mask{padding:14px 8px}}
"""

PANEL_HTML = """
<div id="wbp-mask"><div id="wbp-dlg">
  <div id="wbp-hd"><h3>导入持仓</h3>
    <button id="wbp-x" title="关闭">\u00d7</button></div>
  <div class="wbp-pane">
    <div class="wbp-hint">\u652f\u6301<b>\u6301\u4ed3\u8868</b>\u4e0e<b>\u4ea4\u5272\u5355\uff08\u5bf9\u8d26\u5355\u6d41\u6c34\uff09</b>\uff1a\u4ece\u4e1c\u65b9\u8d22\u5bcc / \u540c\u82b1\u987a / \u5238\u5546\u5bfc\u51fa\u540e\u76f4\u63a5\u7c98\u8d34\uff0c\u6216\u9009\u6587\u4ef6\u3002\u4ea4\u5272\u5355\u4f1a\u6309\u4e70\u5356\u7d2f\u8ba1\u8fd8\u539f\u51fa\u5f53\u524d\u6301\u4ed3\u4e0e<b>\u542b\u8d39\u6210\u672c</b>\u3002</div>
    <input type="file" id="wbp-file" accept=".csv,.txt,.tsv,.xls,.xlsx"
      style="font-size:13px;margin-bottom:10px">
    <textarea id="wbp-ta" placeholder="\u628a\u6301\u4ed3\u8868\u6216\u4ea4\u5272\u5355\u7c98\u5230\u8fd9\u91cc"></textarea>
    <div class="wbp-row">
      <button class="wbp-btn" id="wbp-parse">\u89e3\u6790</button>
      <button class="wbp-btn g" id="wbp-sample">\u586b\u5165\u793a\u4f8b</button>
      <button class="wbp-btn g" id="wbp-clear">\u6e05\u7a7a</button>
    </div>
    <div id="wbp-err" class="wbp-err"></div>
    <div id="wbp-step2" style="display:none">
      <div class="wbp-map" id="wbp-map"></div>
      <div id="wbp-tbl"></div>
      <div class="wbp-row">
        <button class="wbp-btn" id="wbp-save">\u4fdd\u5b58\u5e76\u91cd\u65b0\u751f\u6210</button>
        <button class="wbp-btn g" id="wbp-saveonly">\u4ec5\u4fdd\u5b58</button>
        <span id="wbp-msg" style="font-size:13px"></span>
      </div>
      <pre id="wbp-log"></pre>
    </div>
  </div>
</div></div>
"""
