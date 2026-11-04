# -*- coding: utf-8 -*-
"""登录 / 注册页面。单文件、无外部依赖，与看板共用一套 CSS 变量。"""

LOGIN_PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A 股复盘工作台 · 登录</title><style>__CSS__
body{display:flex;align-items:center;justify-content:center;min-height:100vh;
  background:linear-gradient(160deg,#eef2f8 0%,#f5f6f8 55%,#eaf0f7 100%)}
.auth{width:100%;max-width:400px;padding:16px}
.abox{background:#fff;border-radius:16px;box-shadow:0 10px 40px rgba(31,35,40,.10);
  padding:30px 28px 26px}
.alogo{font-size:21px;font-weight:700;color:#1f2328;text-align:center}
.asub{font-size:12.5px;color:#8a8f98;text-align:center;margin-top:6px;line-height:1.7}
.atabs{display:flex;gap:4px;margin:22px 0 18px;background:#f2f4f6;padding:4px;
  border-radius:10px}
.atab{flex:1;border:none;background:none;padding:8px 0;font-size:13.5px;color:#5f6368;
  cursor:pointer;border-radius:7px;font-family:inherit;font-weight:500}
.atab.on{background:#fff;color:#1a4d8f;font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,.07)}
.afield{margin-bottom:13px}
.alab{font-size:12.5px;color:#5f6368;margin-bottom:5px;display:block}
.ain{width:100%;border:1px solid #dfe3e8;border-radius:9px;padding:10px 12px;
  font-size:14px;font-family:inherit;box-sizing:border-box;transition:border-color .15s}
.ain:focus{outline:none;border-color:#2f5fa8;box-shadow:0 0 0 3px rgba(47,95,168,.10)}
.abtn{width:100%;border:none;border-radius:9px;padding:11px;font-size:14.5px;
  cursor:pointer;background:#2f5fa8;color:#fff;font-weight:600;font-family:inherit;
  margin-top:6px;transition:background .15s}
.abtn:hover{background:#27508f}
.abtn:disabled{background:#c9ced6;cursor:not-allowed}
.amsg{font-size:13px;margin-top:12px;min-height:19px;line-height:1.6}
.amsg.err{color:#b3261e}
.amsg.ok{color:#0b5c31}
.ahint{font-size:11.5px;color:#9aa0a8;margin-top:16px;line-height:1.8;
  padding-top:14px;border-top:1px solid #eef0f3}
</style></head><body>
<div class="auth"><div class="abox">
  <div class="alogo">A 股复盘工作台</div>
  <div class="asub">市场宽度 · 持仓诊断 · 交易行为画像</div>

  <div class="atabs">
    <button class="atab on" id="t-login">登录</button>
    <button class="atab" id="t-reg">注册</button>
  </div>

  <form id="form" autocomplete="on">
    <div class="afield">
      <label class="alab" for="u">用户名</label>
      <input class="ain" id="u" name="username" autocomplete="username"
             placeholder="2~24 位，支持中英文与数字">
    </div>
    <div class="afield">
      <label class="alab" for="p">密码</label>
      <input class="ain" id="p" name="password" type="password"
             autocomplete="current-password" placeholder="至少 6 位">
    </div>
    <div class="afield" id="p2wrap" style="display:none">
      <label class="alab" for="p2">确认密码</label>
      <input class="ain" id="p2" type="password" autocomplete="new-password"
             placeholder="再输入一次">
    </div>
    <button class="abtn" id="go" type="submit">登录</button>
  </form>

  <div class="amsg" id="msg"></div>
  <div class="ahint">
    每个账号拥有独立的自选股、持仓、交割单与复盘报告，互不可见。<br>
    数据保存在本机 users/ 目录，密码以 scrypt 加盐哈希存储，服务仅监听本地回环地址。
  </div>
</div></div>

<script>
var $ = function(i){ return document.getElementById(i); };
var mode = 'login';

function setMode(m){
  mode = m;
  $('t-login').classList.toggle('on', m === 'login');
  $('t-reg').classList.toggle('on', m === 'reg');
  $('p2wrap').style.display = (m === 'reg') ? '' : 'none';
  $('go').textContent = (m === 'reg') ? '注册并进入' : '登录';
  $('p').setAttribute('autocomplete', m === 'reg' ? 'new-password' : 'current-password');
  $('msg').textContent = '';
  $('msg').className = 'amsg';
}
$('t-login').onclick = function(){ setMode('login'); };
$('t-reg').onclick = function(){ setMode('reg'); };

function show(text, ok){
  $('msg').textContent = text;
  $('msg').className = 'amsg ' + (ok ? 'ok' : 'err');
}

$('form').addEventListener('submit', function(e){
  e.preventDefault();
  var u = $('u').value.trim(), p = $('p').value;
  if(!u || !p){ show('请填写用户名和密码', false); return; }
  if(mode === 'reg' && p !== $('p2').value){ show('两次输入的密码不一致', false); return; }
  $('go').disabled = true;
  fetch(mode === 'reg' ? '/api/register' : '/api/login', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username: u, password: p})
  }).then(function(r){ return r.json(); }).then(function(d){
    $('go').disabled = false;
    if(d.error){ show(d.error, false); return; }
    show(d.msg || '成功，正在进入…', true);
    setTimeout(function(){ location.href = '/'; }, 500);
  }).catch(function(err){
    $('go').disabled = false;
    show('请求失败：' + err, false);
  });
});

// 还没有任何账号时默认停在注册页，省掉一次点击
fetch('/me').then(function(r){ return r.json(); }).then(function(d){
  if(d.user){ location.href = '/'; return; }
  if(!d.has_users){
    setMode('reg');
    show('首次使用，请先创建一个账号', true);
  }
});
$('u').focus();
</script></body></html>"""
