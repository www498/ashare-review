PANEL_JS = r"""
(function(){
  var $ = function(id){ return document.getElementById(id); };
  var NAME = __NAME__;
  var mask = $('wbp-mask');

  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function isDash(){
    return /dashboard_\d{8}_(am|pm)\.html$/.test(location.pathname);
  }
  function today(){
    var d = new Date();
    return '' + d.getFullYear() + ('0'+(d.getMonth()+1)).slice(-2) + ('0'+d.getDate()).slice(-2);
  }

  // 旧版看板没有预留锚点，这里兜底创建，避免老报告上什么按钮都没有
  function ensureHeaderSlot(){
    var box = document.querySelector('.wbp-hdact');
    if(box) return box;
    var hd = document.querySelector('.hd');
    if(!hd) return null;
    box = document.createElement('span');
    box.className = 'wbp-hdact';
    hd.appendChild(box);
    return box;
  }

  function ensureSlot(key, titleText){
    var s = document.querySelector('[data-slot="' + key + '"]');
    if(s) return s;
    var cards = document.querySelectorAll('.card');
    for(var i = 0; i < cards.length; i++){
      var h2 = cards[i].querySelector('h2');
      if(h2 && h2.textContent.indexOf(titleText) >= 0){
        var sp = document.createElement('span');
        sp.className = 'wbp-slot';
        sp.setAttribute('data-slot', key);
        h2.appendChild(sp);
        return sp;
      }
    }
    return null;
  }

  // ---------- 页头：日期切换 / 即时复盘 / 账号 / 退出 ----------
  function buildHeader(){
    var box = ensureHeaderSlot();
    if(!box) return;
    box.innerHTML =
      (isDash() ? '<select id="wbp-date" title="切换到其它复盘日期"></select>' : '') +
      '<button class="wbp-a" id="wbp-run" title="用当前行情立刻生成一份复盘">生成即时复盘</button>' +
      '<span class="wbp-user"><i>' + esc(NAME.slice(0,1)) + '</i>' + esc(NAME) + '</span>' +
      '<button class="wbp-a ghost" id="wbp-logout">退出</button>';

    $('wbp-logout').onclick = function(){
      fetch('/api/logout', {method:'POST'}).then(function(){ location.href = '/login'; });
    };
    $('wbp-run').onclick = function(){ runNow(this); };
    if($('wbp-date')) loadDates();
  }

  function loadDates(){
    fetch('/list').then(function(r){ return r.json(); }).then(function(d){
      var sel = $('wbp-date'); if(!sel) return;
      var boards = (d.items || []).filter(function(x){ return x.tag === '看板'; });
      if(!boards.length) return;
      var cur = location.pathname.replace('/reports/', '');
      var html = '';
      for(var i=0;i<boards.length;i++){
        var b = boards[i], f = b.url.replace('/reports/', '');
        html += '<option value="' + esc(b.url) + '"' + (f === cur ? ' selected' : '') + '>' +
                esc(b.label.replace('看板', '').trim()) + '</option>';
      }
      sel.innerHTML = html;
      sel.onchange = function(){ location.href = this.value; };
    });
  }

  function runNow(btn){
    var m = location.pathname.match(/dashboard_(\d{8})_(am|pm)\.html$/);
    var now = new Date();
    var mins = now.getHours() * 60 + now.getMinutes();
    var session = mins < 13 * 60 ? 'am' : 'pm';   // 午盘前出「下午怎么盯」，午后出「明天怎么做」
    var date = today();
    var t0 = Date.now();
    btn.disabled = true; btn.textContent = '生成中…';
    fetch('/run', {method:'POST', headers:{'Content-Type':'application/json'},
                   body: JSON.stringify({session: session})})
      .then(function(){ poll(btn, date, session, t0); })
      .catch(function(){ btn.disabled = false; btn.textContent = '生成即时复盘'; });
  }

  // 一次完整复盘约 3 分钟（含两次大模型调用）。轮询必须做三件事：
  // 报出当前阶段、报出已等秒数、以及在网络抖动时继续轮询而不是停摆。
  // 之前只写「生成中…」，用户无法区分「在算」和「卡死」，断网后按钮还会永久禁用。
  function poll(btn, date, session, t0){
    var sec = Math.round((Date.now() - t0) / 1000);
    fetch('/status').then(function(r){ return r.json(); }).then(function(d){
      if(d.running){
        if(sec > 780){
          btn.disabled = false; btn.textContent = '生成即时复盘';
          alert('已等待 ' + Math.round(sec / 60) + ' 分钟仍未完成。\n\n'
                + (d.tail || '').slice(-300));
          return;
        }
        btn.textContent = '生成中 ' + sec + 's' + (d.step ? ' · ' + d.step : '');
        setTimeout(function(){ poll(btn, date, session, t0); }, 1200);
        return;
      }
      if(d.ok){
        location.href = d.target || ('/reports/dashboard_' + date + '_' + session + '.html');
        return;
      }
      btn.disabled = false; btn.textContent = '生成即时复盘';
      alert('生成失败。\n\n' + ((d.tail || '').slice(-500) || '子进程没有返回输出'));
    }).catch(function(){
      setTimeout(function(){ poll(btn, date, session, t0); }, 2500);
    });
  }

  // ---------- 持仓：导入入口 ----------
  function buildPosSlot(){
    var slot = ensureSlot('pos', '持仓');
    if(!slot) return;
    slot.innerHTML = '<button class="wbp-btnx" id="wbp-open-imp">导入持仓</button>';
    $('wbp-open-imp').onclick = function(){ mask.classList.add('on'); };
  }

  // ---------- 交易行为画像：导入交割单 ----------
  function buildProfileSlot(){
    var slot = ensureSlot('prof', '交易行为画像');
    if(!slot) return;
    slot.innerHTML = '<button class="wbp-btnx" id="wbp-open-stmt">导入交割单</button>';
    $('wbp-open-stmt').onclick = openModal;
  }

  // ---------- 自选股：添加 / 删除 ----------
  function buildWatchSlot(){
    var slot = ensureSlot('wl', '自选股');
    if(!slot) return;
    slot.innerHTML = '<button class="wbp-btnx" id="wbp-wl-toggle">+ 添加</button>';
    $('wbp-wl-toggle').onclick = function(){
      var bar = document.querySelector('.wbp-addbar');
      if(bar){ bar.remove(); return; }
      var card = slot.closest('.card');
      var hint = card.querySelector('.hint');
      var div = document.createElement('div');
      div.className = 'wbp-addbar';
      div.innerHTML = '<input id="wbp-wl-in" placeholder="输入代码，可粘贴多个：600519 或 600519,贵州茅台">' +
                      '<button class="wbp-btnx" id="wbp-wl-add">添加</button>' +
                      '<span class="wbp-tip">沪深京 A 股，回车即可</span>';
      hint.parentNode.insertBefore(div, hint.nextSibling);
      $('wbp-wl-in').focus();
      $('wbp-wl-add').onclick = doAdd;
      $('wbp-wl-in').onkeydown = function(e){ if(e.key === 'Enter') doAdd(); };
    };
  }

  function doAdd(){
    var inp = $('wbp-wl-in'); if(!inp || !inp.value.trim()) return;
    var btn = $('wbp-wl-add'); btn.disabled = true; btn.textContent = '…';
    fetch('/watchlist', {method:'POST', headers:{'Content-Type':'application/json'},
                         body: JSON.stringify({action:'add', codes: inp.value})})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.error){ alert(d.error); btn.disabled = false; btn.textContent = '添加'; return; }
        location.reload();
      })
      .catch(function(){ btn.disabled = false; btn.textContent = '添加'; });
  }

  function bindRowDelete(){
    fetch('/watchlist').then(function(r){ return r.json(); }).then(function(d){
      var items = d.items || [];
      if(!items.length) return;
      // 优先按代码匹配（行上有 data-code），名称匹配只作为老看板的兜底。
      // 行情接口偶尔失败时 items 里 name 为空，纯名称匹配会一个按钮都绑不上。
      var byCode = {}, byName = {};
      for(var j=0;j<items.length;j++){
        byCode[items[j].code] = items[j];
        if(items[j].name) byName[items[j].name] = items[j];
      }
      var rows = document.querySelectorAll('tr.exp');
      for(var i=0;i<rows.length;i++){
        (function(tr){
          var first = tr.querySelector('td'); if(!first) return;
          var code = tr.getAttribute('data-code');
          var txt = first.textContent.replace(/[\u25b8\s]/g, '');
          var hit = (code && byCode[code]) || null;
          if(!hit){
            for(var nm in byName){
              if(txt.indexOf(nm) === 0){ hit = byName[nm]; break; }
            }
          }
          if(!hit) return;
          var tds = tr.querySelectorAll('td');
          var cell = tds[tds.length - 1];
          var b = document.createElement('button');
          b.className = 'wbp-del'; b.title = '从自选股移除'; b.textContent = '\u00d7';
          b.onclick = function(e){
            e.stopPropagation();
            if(!confirm('把「' + hit.name + '」从自选股里移除？')) return;
            b.disabled = true;
            fetch('/watchlist', {method:'POST', headers:{'Content-Type':'application/json'},
                                 body: JSON.stringify({action:'remove', codes:[hit.code]})})
              .then(function(r){ return r.json(); })
              .then(function(res){
                var done = (res.removed || []).indexOf(hit.code) >= 0;
                if(!done){
                  // 后端没删掉就别动页面，否则看起来像成功了、刷新又回来
                  b.disabled = false;
                  alert(res.error || res.msg || '删除失败，请重试');
                  return;
                }
                var next = tr.nextElementSibling;
                if(next && next.classList.contains('det')){
                  next.parentNode.removeChild(next);
                }
                tr.parentNode.removeChild(tr);
              })
              .catch(function(err){
                b.disabled = false;
                alert('删除失败：' + err);
              });
          };
          cell.appendChild(b);
        })(rows[i]);
      }
    }).catch(function(){});
  }

  // ---------- 导入弹窗 ----------
  var ROWS = [];
  function openModal(){ mask.classList.add('on'); }

  $('wbp-x').onclick = function(){ mask.classList.remove('on'); };
  mask.onclick = function(e){ if(e.target === mask) mask.classList.remove('on'); };
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape' && mask.classList.contains('on')) mask.classList.remove('on');
  });

  // ArrayBuffer -> base64。xlsx 是 ZIP 二进制，按文本读只会得到 PK 开头的乱码
  function toB64(buf){
    var b = new Uint8Array(buf), s = '', chunk = 0x8000;
    for(var i = 0; i < b.length; i += chunk){
      s += String.fromCharCode.apply(null, b.subarray(i, i + chunk));
    }
    return btoa(s);
  }

  $('wbp-file').addEventListener('change', function(e){
    var f = e.target.files[0]; if(!f) return;
    var err = $('wbp-err'), ta = $('wbp-ta');
    err.textContent = '';
    ta.value = '';
    ta.placeholder = '\u5df2\u9009\u62e9 ' + f.name + '\uff0c\u6b63\u5728\u89e3\u6790\u2026';
    e.target.value = '';        // 允许重复选择同一个文件
    var r = new FileReader();
    r.onload = function(){
      // 一律发送原始字节：后端按文件头判断 xlsx / 按候选编码试 GBK，
      // 浏览器端猜编码只会把券商导出的 GBK CSV 读成乱码
      fetch('/upload', {method:'POST', headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({name: f.name, data: toB64(r.result)})})
        .then(function(x){ return x.json(); })
        .then(function(d){
          if(d.error){
            ta.placeholder = '\u628a\u6301\u4ed3\u8868\u6216\u4ea4\u5272\u5355\u7c98\u5230\u8fd9\u91cc';
            err.textContent = d.error; return;
          }
          if(!d.rows || !d.rows.length){
            ta.placeholder = '\u628a\u6301\u4ed3\u8868\u6216\u4ea4\u5272\u5355\u7c98\u5230\u8fd9\u91cc';
            err.textContent = '\u6587\u4ef6\u91cc\u6ca1\u6709\u8bc6\u522b\u5230\u6caa\u6df1\u4eac A \u80a1\u4ee3\u7801'; return;
          }
          ROWS = d.rows; render(d);
          ta.placeholder = '\u5df2\u89e3\u6790 ' + f.name + '\uff0c\u6570\u91cf\u4e0e\u6210\u672c\u53ef\u5728\u4e0b\u8868\u76f4\u63a5\u6539';
        })
        .catch(function(ex){
          ta.placeholder = '\u628a\u6301\u4ed3\u8868\u6216\u4ea4\u5272\u5355\u7c98\u5230\u8fd9\u91cc';
          err.textContent = '\u4e0a\u4f20\u5931\u8d25\uff1a' + ex;
        });
    };
    r.readAsArrayBuffer(f);
  });

  $('wbp-sample').onclick = function(){
    fetch('/sample').then(function(r){ return r.json(); }).then(function(d){
      $('wbp-ta').value = d.text; parse();
    });
  };
  $('wbp-clear').onclick = function(){
    $('wbp-ta').value = ''; $('wbp-step2').style.display = 'none';
    $('wbp-err').textContent = ''; $('wbp-msg').textContent = '';
  };
  $('wbp-parse').onclick = parse;

  function parse(){
    var text = $('wbp-ta').value.trim();
    $('wbp-err').textContent = '';
    if(!text){ $('wbp-err').textContent = '\u5148\u7c98\u8d34\u5185\u5bb9\u6216\u9009\u6587\u4ef6'; return; }
    fetch('/parse', {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify({text: text})})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.error){ $('wbp-err').textContent = d.error; return; }
        if(!d.rows || !d.rows.length){
          $('wbp-err').textContent = '\u6ca1\u6709\u8bc6\u522b\u5230\u6caa\u6df1\u4eac A \u80a1\u4ee3\u7801\uff0c\u68c0\u67e5\u4e00\u4e0b\u8868\u683c\u5185\u5bb9'; return;
        }
        ROWS = d.rows; render(d);
      })
      .catch(function(e){ $('wbp-err').textContent = '\u8bf7\u6c42\u5931\u8d25\uff1a' + e; });
  }

  function render(d){
    var m = d.meta || {};
    var kind = m.kind === 'statement' ? '\u4ea4\u5272\u5355' : '\u6301\u4ed3\u8868';
    var names = {code:'\u4ee3\u7801', name:'\u540d\u79f0', shares:'\u6570\u91cf',
                 cost:'\u6210\u672c\u4ef7', price:'\u73b0\u4ef7'};
    var h = '\u8bc6\u522b\u4e3a <b>' + kind + '</b>\uff0c\u5171 <b>' + d.rows.length + '</b> \u53ea\u80a1\u7968';
    if(m.columns && Object.keys(m.columns).length){
      var ps = [];
      for(var k in m.columns){ ps.push((names[k] || k) + '=\u7b2c' + (m.columns[k] + 1) + '\u5217'); }
      h += '<br>\u5217\u6620\u5c04\uff1a' + ps.join('\u3000');
    }
    var pc = 0;
    for(var i=0;i<d.rows.length;i++){
      if(d.rows[i].shares > 0 && d.rows[i].cost > 0) pc++;
    }
    h += '<br>\u5176\u4e2d <b>' + pc + '</b> \u53ea\u6709\u5b8c\u6574\u6301\u4ed3\uff08\u6570\u91cf+\u6210\u672c\uff09';
    if(d.statement){
      h += '<br><span class="wbp-ok">\u4ea4\u5272\u5355\u5df2\u5165\u5e93\uff0c\u91cd\u65b0\u751f\u6210\u540e\u53ef\u770b\u5230\u4ea4\u6613\u884c\u4e3a\u753b\u50cf</span>';
    }else if(kind === '\u4ea4\u5272\u5355'){
      h += '<br><span class="wbp-err">\u4ea4\u5272\u5355\u672a\u80fd\u5165\u5e93\uff0c\u753b\u50cf\u5c06\u65e0\u6cd5\u751f\u6210</span>';
    }
    $('wbp-map').innerHTML = h;

    var t = '<table><tr><th>\u4ee3\u7801</th><th>\u540d\u79f0</th><th class="n">\u6570\u91cf</th>' +
            '<th class="n">\u6210\u672c\u4ef7</th><th class="n">\u5e02\u503c</th></tr>';
    for(var j=0;j<d.rows.length;j++){
      var x = d.rows[j];
      var mv = (x.price && x.shares)
        ? (x.shares * x.price).toLocaleString('zh-CN', {maximumFractionDigits: 0}) : '\u2014';
      t += '<tr><td>' + esc(x.code) + '</td>' +
           '<td><input data-i="' + j + '" data-k="name" value="' + esc(x.name || '') + '"></td>' +
           '<td><input data-i="' + j + '" data-k="shares" value="' + (x.shares == null ? '' : x.shares) +
           '" style="text-align:right"></td>' +
           '<td><input data-i="' + j + '" data-k="cost" value="' + (x.cost == null ? '' : x.cost) +
           '" style="text-align:right"></td>' +
           '<td class="n" id="wbp-mv' + j + '">' + mv + '</td></tr>';
    }
    t += '</table>';
    $('wbp-tbl').innerHTML = t;
    $('wbp-step2').style.display = '';
    $('wbp-msg').textContent = '';
  }

  document.addEventListener('input', function(e){
    var el = e.target;
    if(!el.dataset || el.dataset.k === undefined) return;
    var i = +el.dataset.i, k = el.dataset.k;
    ROWS[i][k] = (k === 'name') ? el.value : (el.value === '' ? null : parseFloat(el.value));
    var mv = $('wbp-mv' + i);
    if(mv){
      var x = ROWS[i];
      mv.textContent = (x.price && x.shares)
        ? (x.shares * x.price).toLocaleString('zh-CN', {maximumFractionDigits: 0}) : '\u2014';
    }
  });

  function save(thenRun){
    var body = ROWS.map(function(x){
      return {code: x.code, name: x.name || '', shares: x.shares || null, cost: x.cost || null};
    });
    fetch('/save', {method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({rows: body})})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.error){ $('wbp-msg').innerHTML = '<span class="wbp-err">' + esc(d.error) + '</span>'; return; }
        var okMsg = '\u5df2\u4fdd\u5b58 ' + d.saved +
          ' \u53ea\uff08' + d.withpos + ' \u53ea\u5e26\u6301\u4ed3\uff09';
        if(d.statement){
          okMsg += ' \u00b7 \u4ea4\u5272\u5355\u5df2\u5165\u5e93\uff0c\u751f\u6210\u540e\u53ef\u89c1\u884c\u4e3a\u753b\u50cf';
        }
        $('wbp-msg').innerHTML = '<span class="wbp-ok">' + okMsg + '</span>';
        if(thenRun){ startRegen(); } else { setTimeout(function(){ location.reload(); }, 700); }
      })
      .catch(function(e){
        $('wbp-msg').innerHTML = '<span class="wbp-err">\u4fdd\u5b58\u5931\u8d25\uff1a' + esc(e) + '</span>';
      });
  }
  $('wbp-save').onclick = function(){ save(true); };
  $('wbp-saveonly').onclick = function(){ save(false); };

  function startRegen(){
    var log = $('wbp-log'); log.style.display = 'block'; log.textContent = '\u6b63\u5728\u53d6\u6570\u2026';
    var now = new Date(), mins = now.getHours() * 60 + now.getMinutes();
    var session = mins < 13 * 60 ? 'am' : 'pm';
    var t0 = Date.now();
    fetch('/run', {method:'POST', headers:{'Content-Type':'application/json'},
                   body: JSON.stringify({session: session})})
      .then(function(){ pollRegen(session, t0); })
      .catch(function(){ log.textContent = '\u542f\u52a8\u5931\u8d25\uff0c\u68c0\u67e5\u5de5\u4f5c\u53f0\u662f\u5426\u8fd8\u5728\u8fd0\u884c'; });
  }
  function pollRegen(session, t0){
    var sec = Math.round((Date.now() - t0) / 1000);
    fetch('/status').then(function(r){ return r.json(); }).then(function(d){
      var head = sec + 's' + (d.step ? ' \u00b7 ' + d.step : '');
      $('wbp-log').textContent = head + '\n\n' + (d.tail || '');
      if(d.running){
        if(sec > 780){
          $('wbp-log').textContent = '\u5df2\u7b49\u5f85 ' + Math.round(sec / 60)
            + ' \u5206\u949f\u4ecd\u672a\u5b8c\u6210\uff0c\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u91cd\u8bd5\u3002\n\n' + (d.tail || '');
          return;
        }
        setTimeout(function(){ pollRegen(session, t0); }, 1200);
        return;
      }
      if(d.ok){ location.href = d.target || ('/reports/dashboard_' + today() + '_' + session + '.html'); }
      else { $('wbp-log').textContent = '\u751f\u6210\u5931\u8d25\uff1a\n\n' + ((d.tail || '').slice(-800) || '\u5b50\u8fdb\u7a0b\u6ca1\u6709\u8fd4\u56de\u8f93\u51fa'); }
    }).catch(function(){
      setTimeout(function(){ pollRegen(session, t0); }, 2500);
    });
  }

  // ---------- 启动 ----------
  buildHeader();
  buildPosSlot();
  buildProfileSlot();
  buildWatchSlot();
  bindRowDelete();
})();
"""


def inject(html, enabled=True, username=None):
    """把内联操作层注入到一个完整 HTML 页面的 </body> 之前。

    enabled=False 时原样返回：静态双击打开的看板没有后端，
    显示点了没反应的按钮比不显示更糟。
    """
    import json

    from .panel import PANEL_CSS, PANEL_HTML

    if not enabled or not html or "</body>" not in html:
        return html
    js = PANEL_JS.replace("__NAME__", json.dumps(username or "", ensure_ascii=False))
    block = "<style>" + PANEL_CSS + "</style>" + PANEL_HTML + "<script>" + js + "</script>"
    return html.replace("</body>", block + "</body>", 1)
