# -*- coding: utf-8 -*-
"""
注入式操作面板。

目的：让用户只打开一个页面就能完成全部操作 —— 看板、导入持仓、重新生成复盘、
切换时段与历史日期，不用再记第二个地址、也不用回到命令行。

实现方式：把一段自包含的 CSS + HTML + JS 注入到 importer 托管的每个 HTML 页面
（首页 / 看板 / 历史趋势）的 </body> 之前。看板本身仍是单文件零依赖的静态页，
直接双击打开时不含这段面板；只有通过本地服务访问时才出现，
因为导入与重跑必须有后端才能工作。

命名统一用 wbp- 前缀，避免和 web.py 既有的 tr.exp 展开脚本冲突。
"""

PANEL_CSS = """
#wbp-fab{position:fixed;right:22px;bottom:22px;z-index:9998;display:flex;gap:8px;
  align-items:center;background:#2f5fa8;color:#fff;border:none;border-radius:999px;
  padding:12px 20px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit;
  box-shadow:0 4px 16px rgba(47,95,168,.35);transition:transform .15s,background .15s}
#wbp-fab:hover{background:#27508f;transform:translateY(-2px)}
#wbp-mask{position:fixed;inset:0;z-index:9999;background:rgba(24,28,34,.55);
  display:none;align-items:flex-start;justify-content:center;overflow:auto;padding:40px 16px}
#wbp-mask.on{display:flex}
#wbp-dlg{background:#fff;border-radius:14px;width:100%;max-width:860px;
  box-shadow:0 18px 50px rgba(0,0,0,.3);overflow:hidden;animation:wbpIn .18s ease-out}
@keyframes wbpIn{from{opacity:0;transform:translateY(-12px)}to{opacity:1;transform:none}}
#wbp-hd{display:flex;align-items:center;justify-content:space-between;
  padding:16px 20px;border-bottom:1px solid #eef0f3;background:#fafbfc}
#wbp-hd h3{margin:0;font-size:16px;color:#1f2328;font-weight:600}
.wbp-who{margin-left:auto;margin-right:10px;font-size:12.5px;color:#5f6368;
  background:#eef2f8;padding:3px 10px;border-radius:999px}
.wbp-out{background:none;border:1px solid #dfe3e8;border-radius:7px;color:#5f6368;
  font-size:12px;padding:4px 11px;cursor:pointer;margin-right:8px;font-family:inherit}
.wbp-out:hover{border-color:#b3261e;color:#b3261e}
#wbp-x{background:none;border:none;font-size:22px;line-height:1;color:#8a9099;
  cursor:pointer;padding:0 4px}
#wbp-x:hover{color:#1f2328}
#wbp-tabs{display:flex;gap:4px;padding:12px 20px 0;border-bottom:1px solid #eef0f3}
.wbp-tab{background:none;border:none;padding:8px 14px;font-size:13.5px;color:#5f6368;
  cursor:pointer;border-radius:8px 8px 0 0;font-family:inherit;border-bottom:2px solid transparent}
.wbp-tab:hover{background:#f6f8fa;color:#1f2328}
.wbp-tab.on{color:#1a4d8f;font-weight:600;border-bottom-color:#2f5fa8;background:#fff}
.wbp-pane{display:none;padding:18px 20px 22px}
.wbp-pane.on{display:block}
.wbp-hint{font-size:12.5px;color:#5f6368;line-height:1.8;margin-bottom:12px}
#wbp-ta{width:100%;height:132px;border:1px solid #dfe3e8;border-radius:8px;padding:10px;
  font-family:ui-monospace,Consolas,monospace;font-size:12.5px;resize:vertical;
  line-height:1.6;box-sizing:border-box}
#wbp-ta:focus{outline:none;border-color:#2f5fa8}
.wbp-btn{border:none;border-radius:8px;padding:9px 18px;font-size:13.5px;cursor:pointer;
  background:#2f5fa8;color:#fff;font-weight:500;font-family:inherit}
.wbp-btn:hover{background:#27508f}
.wbp-btn:disabled{background:#c9ced6;cursor:not-allowed}
.wbp-btn.g{background:#eef2f8;color:#1a4d8f}
.wbp-btn.g:hover{background:#e2eaf6}
.wbp-row{margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.wbp-map{font-size:12.5px;color:#5f6368;background:#f6f8fa;border-radius:8px;
  padding:10px 12px;margin:12px 0;line-height:1.9}
.wbp-map b{color:#1a4d8f}
#wbp-tbl{max-height:280px;overflow:auto}
#wbp-tbl table{width:100%;border-collapse:collapse;font-size:12.5px}
#wbp-tbl th{text-align:left;padding:6px;border-bottom:1px solid #e6e8eb;color:#5f6368;
  font-weight:600;position:sticky;top:0;background:#fff}
#wbp-tbl td{padding:4px 6px;border-bottom:1px solid #f2f4f6}
#wbp-tbl th.n,#wbp-tbl td.n{text-align:right;font-variant-numeric:tabular-nums}
#wbp-tbl input{width:100%;border:1px solid #e6e8eb;border-radius:5px;padding:4px 6px;
  font-size:12.5px;font-variant-numeric:tabular-nums;box-sizing:border-box;font-family:inherit}
#wbp-tbl input:focus{outline:none;border-color:#2f5fa8}
.wbp-err{color:#b3261e;font-size:13px;margin-top:8px}
.wbp-ok{color:#0b5c31;font-size:13px}
#wbp-log{background:#1f2328;color:#e6e8eb;border-radius:8px;padding:12px;font-size:11.5px;
  max-height:200px;overflow:auto;white-space:pre-wrap;margin-top:12px;display:none;
  font-family:ui-monospace,Consolas,monospace}
.wbp-links{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.wbp-links a{display:flex;justify-content:space-between;align-items:center;
  padding:10px 12px;border:1px solid #e6e8eb;border-radius:8px;text-decoration:none;
  color:#1f2328;font-size:13.5px;transition:border-color .15s,background .15s}
.wbp-links a:hover{border-color:#2f5fa8;background:#f7f9fc}
.wbp-links .t{color:#8a9099;font-size:12px}
.wbp-sp{display:inline-block;width:13px;height:13px;border:2px solid #fff;
  border-top-color:transparent;border-radius:50%;animation:wbpSp .7s linear infinite;
  vertical-align:-2px;margin-right:6px}
@keyframes wbpSp{to{transform:rotate(360deg)}}
@media(max-width:620px){#wbp-fab{right:14px;bottom:14px;padding:10px 16px;font-size:13px}
  #wbp-mask{padding:16px 8px}}
"""

PANEL_HTML = """
<button id="wbp-fab" title="导入持仓 / 重新生成复盘">\u2699 \u64cd\u4f5c</button>
<div id="wbp-mask"><div id="wbp-dlg">
  <div id="wbp-hd"><h3>\u64cd\u4f5c\u9762\u677f</h3>
    <button id="wbp-x" title="\u5173\u95ed">\u00d7</button></div>
  <div id="wbp-tabs">
    <button class="wbp-tab on" data-p="imp">\u5bfc\u5165\u6301\u4ed3</button>
    <button class="wbp-tab" data-p="wl">\u81ea\u9009\u80a1</button>
    <button class="wbp-tab" data-p="run">\u91cd\u65b0\u751f\u6210\u590d\u76d8</button>
    <button class="wbp-tab" data-p="nav">\u5207\u6362\u62a5\u8868</button>
  </div>

  <div class="wbp-pane on" id="wbp-p-imp">
    <div class="wbp-hint">\u4ece\u4e1c\u65b9\u8d22\u5bcc / \u540c\u82b1\u987a / \u5238\u5546\u5bfc\u51fa\u7684<b>\u6301\u4ed3\u8868</b>\u6216<b>\u4ea4\u5272\u5355\uff08\u5bf9\u8d26\u5355\u6d41\u6c34\uff09</b>\u5747\u53ef\uff0c\u7c98\u8d34\u6216\u9009\u6587\u4ef6\u3002\u4ea4\u5272\u5355\u4f1a\u81ea\u52a8\u6309\u4e70\u5356\u7d2f\u8ba1\u8fd8\u539f\u51fa\u5f53\u524d\u6301\u4ed3\u4e0e\u542b\u8d39\u6210\u672c\u3002</div>
    <input type="file" id="wbp-file" accept=".csv,.txt,.tsv,.xls,.xlsx" style="font-size:13px;margin-bottom:10px">
    <textarea id="wbp-ta" placeholder="\u628a\u6301\u4ed3\u8868\u7c98\u5230\u8fd9\u91cc"></textarea>
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
    </div>
  </div>

  <div class="wbp-pane" id="wbp-p-wl">
    <div class="wbp-hint">\u6dfb\u52a0\u65f6\u53ef\u7c98\u8d34\u591a\u4e2a\u4ee3\u7801\uff08\u7a7a\u683c\u3001\u9017\u53f7\u6216\u6362\u884c\u5206\u9694\uff09\uff0c\u652f\u6301\u300c600519\u300d\u6216\u300c600519,\u8d35\u5dde\u8305\u53f0\u300d\u3002\u5220\u9664\u6301\u4ed3\u6807\u7684\u4f1a\u540c\u6b65\u4ece positions.csv \u79fb\u9664\u3002</div>
    <div class="wbp-row">
      <input id="wbp-wl-in" placeholder="600519 000001,\u5e73\u5b89\u94f6\u884c"
        style="flex:1;min-width:220px;border:1px solid #dfe3e8;border-radius:8px;padding:8px 10px;font-size:13px;font-family:inherit">
      <button class="wbp-btn" id="wbp-wl-add">\u6dfb\u52a0</button>
    </div>
    <div id="wbp-wl-msg" style="font-size:13px;margin-top:8px"></div>
    <div id="wbp-wl-list" style="margin-top:12px;max-height:320px;overflow:auto"></div>
  </div>

  <div class="wbp-pane" id="wbp-p-run">
    <div class="wbp-hint">\u91cd\u65b0\u53d6\u6570\u5e76\u751f\u6210\u62a5\u8868\u4e0e\u770b\u677f\u3002\u6536\u76d8\u590d\u76d8\u542b\u6ce2\u52a8\u7387\u533a\u95f4\uff0c\u8017\u65f6\u8f83\u957f\uff1b\u5348\u76d8\u590d\u76d8\u8bf7\u5728 11:30-13:00 \u4e4b\u95f4\u8dd1\u624d\u6709\u610f\u4e49\u3002\u5b8c\u6210\u540e\u4f1a\u81ea\u52a8\u8df3\u8f6c\u5230\u65b0\u770b\u677f\u3002</div>
    <div class="wbp-row">
      <button class="wbp-btn" id="wbp-run-pm">\u751f\u6210\u6536\u76d8\u590d\u76d8</button>
      <button class="wbp-btn g" id="wbp-run-am">\u751f\u6210\u5348\u76d8\u590d\u76d8</button>
      <button class="wbp-btn g" id="wbp-run-off">\u79bb\u7ebf\u91cd\u653e\uff08\u4e0d\u8054\u7f51\uff09</button>
    </div>
    <pre id="wbp-log"></pre>
  </div>

  <div class="wbp-pane" id="wbp-p-nav">
    <div class="wbp-hint">\u5df2\u751f\u6210\u7684\u62a5\u8868\u4e0e\u770b\u677f\u3002</div>
    <div class="wbp-links" id="wbp-nav"></div>
  </div>
</div></div>
"""
