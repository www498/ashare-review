PANEL_JS = r"""
(function(){
  var R = [], $ = function(i){return document.getElementById(i);};
  var mask = $('wbp-mask');

  // 会话失效时跳回登录页，避免用户对着一个点不动的面板发呆
  function guard(d){
    if(d && d.need_login){ location.href = '/login'; return true; }
    return false;
  }
  var out = $('wbp-logout');
  if(out){
    out.onclick = function(){
      fetch('/api/logout', {method:'POST'})
        .then(function(){ location.href = '/login'; });
    };
  }

  function open(){ mask.classList.add('on'); }
  function close(){ mask.classList.remove('on'); }
  $('wbp-fab').onclick = open;
  $('wbp-x').onclick = close;
  mask.onclick = function(e){ if(e.target === mask) close(); };
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape' && mask.classList.contains('on')) close();
  });

  // Tab 切换
  var tabs = document.querySelectorAll('.wbp-tab');
  for(var i=0;i<tabs.length;i++){
    tabs[i].onclick = function(){
      for(var j=0;j<tabs.length;j++){ tabs[j].classList.remove('on'); }
      this.classList.add('on');
      var panes = document.querySelectorAll('.wbp-pane');
      for(var k=0;k<panes.length;k++){ panes[k].classList.remove('on'); }
      $('wbp-p-' + this.dataset.p).classList.add('on');
      if(this.dataset.p === 'nav'){ loadNav(); }
      if(this.dataset.p === 'wl'){ loadWL(); }
    };
  }

  // ---- 导入 ----
  // xlsx 是 ZIP 二进制，readAsText 只能得到 PK... 乱码。
  // 二进制格式走 /upload 让后端用 openpyxl 解析；纯文本仍在前端读，省一次往返。
  $('wbp-file').addEventListener('change', function(e){
    var f = e.target.files[0]; if(!f) return;
    $('wbp-err').textContent = '';
    var bin = /\.(xlsx|xlsm|xls)$/i.test(f.name);
    var r = new FileReader();
    if(bin){
      $('wbp-ta').value = '';
      $('wbp-ta').placeholder = '已选择 ' + f.name + '，正在解析…';
      r.onload = function(){
        fetch('/upload', {method:'POST', headers:{'Content-Type':'application/json'},
                          body: JSON.stringify({name:f.name, data:r.result})})
          .then(function(x){return x.json();})
          .then(function(d){
            $('wbp-ta').placeholder = '把持仓表粘到这里';
            if(d.error){ $('wbp-err').textContent = d.error; return; }
            if(!d.rows || !d.rows.length){
              $('wbp-err').textContent = '文件里没有识别到沪深京 A 股代码'; return;
            }
            R = d.rows; render(d);
          })
          .catch(function(err){
            $('wbp-ta').placeholder = '把持仓表粘到这里';
            $('wbp-err').textContent = '上传失败：' + err;
          });
      };
      r.readAsDataURL(f);
    }else{
      r.onload = function(){ $('wbp-ta').value = r.result; parse(); };
      r.readAsText(f, 'UTF-8');
    }
  });
  $('wbp-sample').onclick = function(){
    fetch('/sample').then(function(r){return r.json();}).then(function(d){
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
    if(!text){ $('wbp-err').textContent = '先粘贴内容或选择文件'; return; }
    fetch('/parse', {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify({text:text})})
      .then(function(r){return r.json();})
      .then(function(d){
        if(guard(d)) return;
        if(d.error){ $('wbp-err').textContent = d.error; return; }
        if(!d.rows || !d.rows.length){
          $('wbp-err').textContent = '没有识别到沪深京 A 股代码，检查表格内容'; return;
        }
        R = d.rows; render(d);
      })
      .catch(function(e){ $('wbp-err').textContent = '请求失败：' + e; });
  }

  function esc(s){
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function render(d){
    var m = d.meta || {};
    var h;
    if(m.kind === 'statement'){
      h = '已识别为<b>交割单</b>（流水 ' + (m.trades||0) + ' 笔' +
          (m.span ? '，' + m.span[0] + ' ~ ' + m.span[1] : '') +
          '），按买卖累计还原出 <b>' + d.rows.length + '</b> 只在持标的。';
      h += '<br>成本为移动加权' + (m.fee_included ? '<b>含手续费</b>' : '') +
           '，已清仓标的自动剔除。';
      if(m.mismatch && m.mismatch.length){
        h += '<br><span style="color:#b3261e">注意：' + m.mismatch.length +
             ' 只与「股份余额」列不一致（可能有送股/转增），请手工核对数量。</span>';
      }
    }else{
      h = '识别到 <b>' + d.rows.length + '</b> 只股票　·　' +
          (m.header ? '表头已识别' : '无表头，按位置解析');
      if(m.columns && Object.keys(m.columns).length){
        var nm = {code:'代码', name:'名称', shares:'数量', cost:'成本价', price:'现价'};
        var ps = [];
        for(var k in m.columns){ ps.push((nm[k]||k) + '=第' + (m.columns[k]+1) + '列'); }
        h += '<br>列映射：' + ps.join('　');
      }
      var pc = d.rows.filter(function(x){return x.shares>0 && x.cost>0;}).length;
      h += '<br>其中 <b>' + pc + '</b> 只有完整持仓（数量+成本），其余按关注处理';
    }
    $('wbp-map').innerHTML = h;

    var t = '<table><colgroup><col style="width:76px"><col>' +
            '<col style="width:92px"><col style="width:92px"><col style="width:88px">' +
            '</colgroup><tr><th>代码</th><th>名称</th><th class="n">数量</th>' +
            '<th class="n">成本价</th><th class="n">市值</th></tr>';
    for(var i=0;i<d.rows.length;i++){
      var x = d.rows[i];
      t += '<tr><td>' + esc(x.code) + '</td>' +
           '<td><input data-i="'+i+'" data-k="name" value="'+esc(x.name)+'"></td>' +
           '<td><input data-i="'+i+'" data-k="shares" value="'+esc(x.shares)+'" style="text-align:right"></td>' +
           '<td><input data-i="'+i+'" data-k="cost" value="'+esc(x.cost)+'" style="text-align:right"></td>' +
           '<td class="n" id="wbp-mv'+i+'">' + mv(x) + '</td></tr>';
    }
    $('wbp-tbl').innerHTML = t + '</table>';
    $('wbp-step2').style.display = '';
    $('wbp-msg').textContent = '';
  }

  function mv(x){
    return (x.price && x.shares)
      ? (x.shares * x.price).toLocaleString('zh-CN', {maximumFractionDigits:0}) : '—';
  }

  $('wbp-tbl').addEventListener('input', function(e){
    var el = e.target;
    if(!el.dataset || el.dataset.k === undefined) return;
    var i = +el.dataset.i, k = el.dataset.k;
    R[i][k] = (k === 'name') ? el.value
      : (el.value === '' ? null : parseFloat(el.value));
    var c = $('wbp-mv' + i);
    if(c) c.textContent = mv(R[i]);
  });

  function save(then){
    var body = R.map(function(x){
      return {code:x.code, name:x.name||'', shares:x.shares||null, cost:x.cost||null};
    });
    $('wbp-save').disabled = true; $('wbp-saveonly').disabled = true;
    fetch('/save', {method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({rows:body})})
      .then(function(r){return r.json();})
      .then(function(d){
        $('wbp-save').disabled = false; $('wbp-saveonly').disabled = false;
        if(guard(d)) return;
        if(d.error){ $('wbp-msg').innerHTML = '<span class="wbp-err">'+esc(d.error)+'</span>'; return; }
        $('wbp-msg').innerHTML = '<span class="wbp-ok">已保存 ' + d.saved +
          ' 只（' + d.withpos + ' 只含持仓）</span>';
        if(then) then();
      })
      .catch(function(e){
        $('wbp-save').disabled = false; $('wbp-saveonly').disabled = false;
        $('wbp-msg').innerHTML = '<span class="wbp-err">保存失败：'+esc(e)+'</span>';
      });
  }
  $('wbp-saveonly').onclick = function(){ save(null); };
  $('wbp-save').onclick = function(){
    save(function(){
      document.querySelector('.wbp-tab[data-p="run"]').click();
      run('pm', false);
    });
  };

  // ---- 自选股管理 ----
  function loadWL(){
    var box = $('wbp-wl-list');
    box.innerHTML = '<div class="wbp-hint">加载中…</div>';
    fetch('/watchlist').then(function(r){return r.json();}).then(function(d){
      var it = d.items || [];
      if(!it.length){ box.innerHTML = '<div class="wbp-hint">还没有自选股。</div>'; return; }
      var t = '<table style="width:100%;border-collapse:collapse;font-size:12.5px">' +
              '<tr><th style="text-align:left;padding:6px;border-bottom:1px solid #e6e8eb;color:#5f6368">代码</th>' +
              '<th style="text-align:left;padding:6px;border-bottom:1px solid #e6e8eb;color:#5f6368">名称</th>' +
              '<th style="text-align:right;padding:6px;border-bottom:1px solid #e6e8eb;color:#5f6368">现价</th>' +
              '<th style="text-align:right;padding:6px;border-bottom:1px solid #e6e8eb;color:#5f6368">涨跌</th>' +
              '<th style="text-align:right;padding:6px;border-bottom:1px solid #e6e8eb;color:#5f6368">持仓</th>' +
              '<th style="padding:6px;border-bottom:1px solid #e6e8eb"></th></tr>';
      it.forEach(function(x){
        var pc = (x.pct == null) ? '—'
          : '<span style="color:' + (x.pct>=0 ? '#d94b4b' : '#2b8560') + '">' +
            (x.pct>=0?'+':'') + x.pct.toFixed(2) + '%</span>';
        t += '<tr><td style="padding:5px 6px;border-bottom:1px solid #f2f4f6">' + esc(x.code) + '</td>' +
             '<td style="padding:5px 6px;border-bottom:1px solid #f2f4f6">' + esc(x.name) + '</td>' +
             '<td style="padding:5px 6px;text-align:right;border-bottom:1px solid #f2f4f6">' +
               (x.price != null ? x.price.toFixed(2) : '—') + '</td>' +
             '<td style="padding:5px 6px;text-align:right;border-bottom:1px solid #f2f4f6">' + pc + '</td>' +
             '<td style="padding:5px 6px;text-align:right;border-bottom:1px solid #f2f4f6">' +
               (x.held ? x.shares + ' 股' : '—') + '</td>' +
             '<td style="padding:5px 6px;text-align:right;border-bottom:1px solid #f2f4f6">' +
               '<button class="wbp-btn g wbp-del" data-c="' + esc(x.code) +
               '" style="padding:3px 10px;font-size:12px">删除</button></td></tr>';
      });
      box.innerHTML = t + '</table>';
    });
  }

  $('wbp-wl-add').onclick = function(){
    var v = $('wbp-wl-in').value.trim();
    if(!v){ $('wbp-wl-msg').innerHTML = '<span class="wbp-err">先输入代码</span>'; return; }
    wlPost('add', v);
  };
  $('wbp-wl-in').addEventListener('keydown', function(e){
    if(e.key === 'Enter'){ $('wbp-wl-add').click(); }
  });
  $('wbp-wl-list').addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.wbp-del') : null;
    if(!b) return;
    wlPost('remove', b.dataset.c);
  });

  function wlPost(action, codes){
    fetch('/watchlist', {method:'POST', headers:{'Content-Type':'application/json'},
                         body: JSON.stringify({action:action, codes:codes})})
      .then(function(r){return r.json();})
      .then(function(d){
        if(guard(d)) return;
        if(d.error){ $('wbp-wl-msg').innerHTML = '<span class="wbp-err">'+esc(d.error)+'</span>'; return; }
        $('wbp-wl-msg').innerHTML = '<span class="wbp-ok">'+esc(d.msg)+'</span>' +
          '<span style="color:#8a8f98;margin-left:8px">改动将在下次生成复盘时生效</span>';
        if(action === 'add'){ $('wbp-wl-in').value = ''; }
        loadWL();
      })
      .catch(function(e){ $('wbp-wl-msg').innerHTML = '<span class="wbp-err">请求失败：'+esc(e)+'</span>'; });
  }

  // ---- 重新生成 ----
  var busy = false;
  function run(session, offline){
    if(busy) return;
    busy = true;
    var btns = document.querySelectorAll('#wbp-p-run .wbp-btn');
    for(var i=0;i<btns.length;i++){ btns[i].disabled = true; }
    var log = $('wbp-log');
    log.style.display = '';
    log.textContent = '正在取数…（全市场约 6 秒，含波动率预测会更久）';
    fetch('/run', {method:'POST', headers:{'Content-Type':'application/json'},
                   body: JSON.stringify({session:session, offline:!!offline})})
      .then(function(){ poll(); })
      .catch(function(e){
        busy = false;
        for(var i=0;i<btns.length;i++){ btns[i].disabled = false; }
        log.textContent = '启动失败：' + e;
      });
  }
  function poll(){
    fetch('/status').then(function(r){return r.json();}).then(function(d){
      var log = $('wbp-log');
      log.textContent = d.tail || '…';
      log.scrollTop = log.scrollHeight;
      if(d.running){ setTimeout(poll, 1200); return; }
      busy = false;
      var btns = document.querySelectorAll('#wbp-p-run .wbp-btn');
      for(var i=0;i<btns.length;i++){ btns[i].disabled = false; }
      log.textContent = (d.ok ? '[完成]\n' : '[失败]\n') + (d.tail || '');
      log.scrollTop = log.scrollHeight;
      if(d.ok && d.target){
        log.textContent += '\n\n即将打开新看板…';
        setTimeout(function(){ location.href = d.target; }, 900);
      }
    });
  }
  $('wbp-run-pm').onclick  = function(){ run('pm', false); };
  $('wbp-run-am').onclick  = function(){ run('am', false); };
  $('wbp-run-off').onclick = function(){ run('pm', true); };

  // ---- 切换报表 ----
  function loadNav(){
    var box = $('wbp-nav');
    box.innerHTML = '<div class="wbp-hint">加载中…</div>';
    fetch('/list').then(function(r){return r.json();}).then(function(d){
      var h = '';
      (d.items || []).forEach(function(x){
        h += '<a href="' + x.url + '"><span>' + esc(x.label) + '</span>' +
             '<span class="t">' + esc(x.tag) + '</span></a>';
      });
      box.innerHTML = h || '<div class="wbp-hint">还没有生成任何报表。</div>';
    });
  }
})();
"""


def inject(html, enabled=True, username=None):
    """把操作面板注入到一个完整 HTML 页面的 </body> 之前。

    enabled=False 时原样返回：静态双击打开的看板没有后端，
    显示一个点了没反应的按钮比不显示更糟。
    username 非空时在面板标题栏显示当前账号与退出入口。
    """
    if not enabled or not html or "</body>" not in html:
        return html
    from .panel import PANEL_CSS, PANEL_HTML
    block_html = PANEL_HTML
    if username:
        import html as _h
        safe = _h.escape(str(username))
        block_html = block_html.replace(
            '<button id="wbp-x"',
            f'<span class="wbp-who">{safe}</span>'
            f'<button class="wbp-out" id="wbp-logout">退出</button>'
            f'<button id="wbp-x"')
    block = ("<style>" + PANEL_CSS + "</style>"
             + block_html
             + "<script>" + PANEL_JS + "</script>")
    return html.replace("</body>", block + "</body>", 1)
