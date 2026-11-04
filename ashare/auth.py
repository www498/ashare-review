# -*- coding: utf-8 -*-
"""
账号体系：注册、登录、会话、按账号隔离的数据目录。

为什么用标准库自己实现：
本项目的原则是零第三方依赖（不引 Flask/SQLAlchemy/passlib）。
密码哈希用 hashlib.scrypt（Python 3.6+ 自带，抗 GPU 暴力破解），
会话用 secrets 生成的随机 token，存储用 JSON 文件。
对本地单机工具来说这个强度足够，且不增加任何安装负担。

安全口径（如实说明，不夸大）：
- 密码不以明文或可逆形式保存，只存 scrypt 哈希 + 每人独立的 salt
- 会话 token 为 32 字节密码学随机数，默认 7 天过期
- 服务只监听 127.0.0.1，不处理跨网访问；Cookie 未设 Secure（本地无 HTTPS）
- 这不是面向公网的认证系统，不要把它直接暴露到公网

数据隔离：
每个账号一个目录 users/<uid>/，内含该账号自己的
  watchlist.txt / positions.csv / 交割单 / reports/ / snapshots/
行情类公共缓存（日K、成分股、行业、历史宽度）仍放 data/ 全局共享 —— 
那是市场数据，与账号无关，重复存储会浪费几十 MB 且拖慢首次运行。
"""
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import threading

from .data import ROOT

USERS_DIR = os.path.join(ROOT, "users")
DB_PATH = os.path.join(USERS_DIR, "_accounts.json")
SESSION_DAYS = 7
_LOCK = threading.RLock()

NAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5][A-Za-z0-9_\-.\u4e00-\u9fa5]{1,23}$")

# scrypt 参数：n 越大越慢越安全。16384 在普通机器上约 50~80ms，
# 对交互登录无感，对暴力破解是显著成本。
SCRYPT = {"n": 16384, "r": 8, "p": 1, "dklen": 32}


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def _load():
    if not os.path.exists(DB_PATH):
        return {"users": {}, "sessions": {}}
    try:
        with open(DB_PATH, encoding="utf-8") as f:
            db = json.load(f)
        db.setdefault("users", {})
        db.setdefault("sessions", {})
        return db
    except Exception:
        return {"users": {}, "sessions": {}}


def _save(db):
    os.makedirs(USERS_DIR, exist_ok=True)
    # 先尝试「临时文件 + 原子替换」，避免写一半导致账号库损坏。
    # 某些受保护/受监控的目录会禁止 replace，此时退回直接覆盖写——
    # 文件很小（单次写入通常在一个块内），实际损坏风险可接受。
    tmp = DB_PATH + ".tmp"
    data = json.dumps(db, ensure_ascii=False, indent=1)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, DB_PATH)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        with open(DB_PATH, "w", encoding="utf-8") as f:
            f.write(data)


def _hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT).hex()


def uid_of(username):
    """用户名 -> 目录名。中文用户名不能直接做目录名，用哈希前 12 位兜底。"""
    u = username.strip()
    if re.match(r"^[A-Za-z0-9_\-.]{2,24}$", u):
        return u.lower()
    return "u_" + hashlib.sha256(u.encode("utf-8")).hexdigest()[:12]


def user_dir(uid):
    p = os.path.join(USERS_DIR, uid)
    os.makedirs(os.path.join(p, "reports"), exist_ok=True)
    os.makedirs(os.path.join(p, "snapshots"), exist_ok=True)
    return p


# ---------------- 注册 / 登录 ----------------

def validate(username, password):
    """返回错误信息，None 表示通过。"""
    u = (username or "").strip()
    if not NAME_RE.match(u):
        return "用户名需 2~24 位，可用中英文、数字、下划线，不能以符号开头"
    if len(password or "") < 6:
        return "密码至少 6 位"
    if len(password or "") > 128:
        return "密码过长"
    return None


def register(username, password):
    """返回 (ok, msg, uid)。用户名不区分大小写，防止 Admin/admin 混淆。"""
    err = validate(username, password)
    if err:
        return False, err, None
    u = username.strip()
    key = u.lower()
    with _LOCK:
        db = _load()
        if key in db["users"]:
            return False, "该用户名已被注册", None
        uid = uid_of(u)
        # 两个不同用户名哈希到同一 uid 的概率极低，但仍要防撞
        if any(r.get("uid") == uid for r in db["users"].values()):
            uid = uid + secrets.token_hex(2)
        salt = secrets.token_bytes(16)
        db["users"][key] = {
            "username": u,
            "uid": uid,
            "salt": salt.hex(),
            "hash": _hash(password, salt),
            "created_at": _now(),
            "last_login": None,
        }
        _save(db)
        user_dir(uid)
        _seed_user_files(uid)
        return True, f"注册成功，已为「{u}」创建独立数据空间", uid


def login(username, password):
    """返回 (ok, msg, token, user)。"""
    key = (username or "").strip().lower()
    with _LOCK:
        db = _load()
        rec = db["users"].get(key)
        if not rec:
            # 不区分「用户不存在」与「密码错误」，避免被用来枚举账号
            return False, "用户名或密码错误", None, None
        salt = bytes.fromhex(rec["salt"])
        if not secrets.compare_digest(_hash(password or "", salt), rec["hash"]):
            return False, "用户名或密码错误", None, None
        token = secrets.token_urlsafe(32)
        exp = (dt.datetime.now() + dt.timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
        db["sessions"][token] = {"uid": rec["uid"], "username": rec["username"],
                                 "expires": exp}
        rec["last_login"] = _now()
        _prune(db)
        _save(db)
        user_dir(rec["uid"])
        return True, f"欢迎回来，{rec['username']}", token, {
            "uid": rec["uid"], "username": rec["username"]}


def logout(token):
    with _LOCK:
        db = _load()
        if token and token in db["sessions"]:
            db["sessions"].pop(token, None)
            _save(db)
    return True


def whoami(token):
    """校验会话，返回 {uid, username} 或 None。"""
    if not token:
        return None
    with _LOCK:
        db = _load()
        s = db["sessions"].get(token)
        if not s:
            return None
        try:
            if dt.datetime.fromisoformat(s["expires"]) < dt.datetime.now():
                db["sessions"].pop(token, None)
                _save(db)
                return None
        except Exception:
            return None
        return {"uid": s["uid"], "username": s["username"]}


def change_password(username, old, new):
    err = validate(username, new)
    if err:
        return False, err
    ok, _, _, _ = login(username, old)
    if not ok:
        return False, "原密码不正确"
    key = username.strip().lower()
    with _LOCK:
        db = _load()
        rec = db["users"].get(key)
        salt = secrets.token_bytes(16)
        rec["salt"] = salt.hex()
        rec["hash"] = _hash(new, salt)
        # 改密后踢掉该账号的全部会话，旧 token 立即失效
        db["sessions"] = {t: s for t, s in db["sessions"].items()
                          if s.get("uid") != rec["uid"]}
        _save(db)
    return True, "密码已更新，请重新登录"


def _prune(db):
    now = dt.datetime.now()
    alive = {}
    for t, s in db["sessions"].items():
        try:
            if dt.datetime.fromisoformat(s["expires"]) >= now:
                alive[t] = s
        except Exception:
            continue
    db["sessions"] = alive


def count_users():
    return len(_load()["users"])


def list_users():
    db = _load()
    return [{"username": r["username"], "uid": r["uid"],
             "created_at": r.get("created_at"), "last_login": r.get("last_login")}
            for r in db["users"].values()]


# ---------------- 用户数据空间 ----------------

TEMPLATE_WATCHLIST = """# 自选股清单 —— 粘贴券商自选/持仓即可，格式不限
# 支持：纯代码、代码+名称、Tab 分隔、.SH/.SZ 后缀；沪深京 A 股自动识别
# 以 # 开头的行为注释，会被忽略
# 持仓数据建议在页面「操作 → 导入持仓」里导入，会写入本账号的 positions.csv

600519,贵州茅台
601318,中国平安
600036,招商银行
"""


def _seed_user_files(uid):
    """新账号给一份自选股模板，避免首次运行因清单为空而无内容可看。
    不复制任何既有账号的持仓或交割单 —— 那是别人的隐私数据。"""
    d = user_dir(uid)
    wl = os.path.join(d, "watchlist.txt")
    if not os.path.exists(wl):
        with open(wl, "w", encoding="utf-8") as f:
            f.write(TEMPLATE_WATCHLIST)


def paths(uid):
    """该账号的全部数据路径。uid 为 None 时回退到项目根目录（单用户兼容模式）。"""
    if not uid:
        return {"root": ROOT,
                "watchlist": os.path.join(ROOT, "watchlist.txt"),
                "positions": os.path.join(ROOT, "positions.csv"),
                "reports": os.path.join(ROOT, "reports"),
                "snapshots": os.path.join(ROOT, "data", "snapshots")}
    d = user_dir(uid)
    return {"root": d,
            "watchlist": os.path.join(d, "watchlist.txt"),
            "positions": os.path.join(d, "positions.csv"),
            "reports": os.path.join(d, "reports"),
            "snapshots": os.path.join(d, "snapshots")}
