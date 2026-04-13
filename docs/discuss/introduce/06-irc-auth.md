# 第六章：IRC 与认证管理

> 预计阅读：20 分钟

## 概述

本章覆盖两个模块：
- **IrcManager**：管理本地 ergo IRC 服务器和 WeeChat 客户端
- **auth.py**：OIDC 认证与 token 管理

> 代码位置：`zchat/cli/irc_manager.py`、`zchat/cli/auth.py`

## IrcManager：ergo 服务器管理

### 启动 ergo

```python
# irc_manager.py:35-114
def daemon_start(self, port_override=None):
    # 1. 检查是否是本地服务器
    if server not in ("127.0.0.1", "localhost", "::1"):
        print("IRC server is remote, no local daemon needed.")
        return
    
    # 2. 检查端口是否已占用
    if self._port_in_use(port):
        print(f"ergo already running on port {port}")
        return
    
    # 3. 创建项目级 ergo 数据目录
    ergo_data_dir = os.path.join(project_dir, "ergo")
    
    # 4. 复制 languages 目录（如果缺失）
    system_ergo = "~/.local/share/ergo"
    if not os.path.isdir(os.path.join(ergo_data_dir, "languages")):
        shutil.copytree(system_ergo + "/languages", ergo_data_dir + "/languages")
    
    # 5. 生成 ergo 配置
    result = subprocess.run(["ergo", "defaultconfig"], capture_output=True)
    config_text = result.stdout
    
    # 6. 修补配置：改端口、删 IPv6、删 TLS
    config_text = config_text.replace('"127.0.0.1:6667":', f'"127.0.0.1:{port}":')
    
    # 7. 注入 OIDC 认证脚本（如果有凭证）
    if get_credentials():
        self._inject_auth_script(ergo_data_dir, ergo_conf)
    
    # 8. 删除残留锁文件
    # 9. 启动 ergo 子进程
    proc = subprocess.Popen(["ergo", "run", "--conf", ergo_conf], ...)
    
    # 10. 保存 PID 到 state.json
    self._state["irc"]["daemon_pid"] = proc.pid
```

**每个项目有独立的 ergo 实例**，配置和数据存储在 `~/.zchat/projects/<name>/ergo/`。

> 引用：`zchat/cli/irc_manager.py:35-114`

### 启动 WeeChat

```python
# irc_manager.py:177-252
def start_weechat(self, nick_override=None):
    # 1. 加载 tmuxp session
    if os.path.isfile(tmuxp_path):
        subprocess.run(["tmuxp", "load", "-d", tmuxp_path])
    
    # 2. 构建 WeeChat 启动命令
    cmd = (
        f"weechat -d {weechat_home} -r '"
        f"/server add {srv_name} {server}/{port}{tls_flag} -nicks={nick}"
        f"; /set irc.server.{srv_name}.autojoin \"{autojoin}\""
        f"{sasl_cmds}"          # SASL 认证（如果有）
        f"; /connect {srv_name}"
        f"{load_plugin}'"       # 加载 zchat.py 插件
    )
    
    # 3. 在 tmux window 中运行
    weechat_window = find_window(self.tmux_session, "weechat")
    if weechat_window:
        pane.send_keys(cmd, enter=True)   # tmuxp 已创建 window
    else:
        self.tmux_session.new_window(window_name="weechat", window_shell=cmd)
```

关键细节：
- **每个项目有独立的 WeeChat 配置目录**：`~/.zchat/projects/<name>/.weechat/`
- **服务器名格式**：`<project>-ergo`（如 `local-ergo`）
- **自动加入频道**：从 `config.toml` 的 `default_channels` 读取
- **插件自动加载**：查找 zchat.py 并用 `/script load` 加载

> 引用：`zchat/cli/irc_manager.py:177-252`

### WeeChat 配置缓存问题

WeeChat 会将 IRC 服务器配置持久化到 `.weechat/irc.conf`。当 `config.toml` 中的服务器地址改变后，WeeChat 的 `/server add` 命令会提示 "server already exists" 并忽略新配置。

**当前 workaround**：删除 `~/.zchat/projects/<name>/.weechat/irc.conf`。

> 引用：GitHub issue ezagent42/zchat#42

### 插件查找顺序

```python
# irc_manager.py:302-315
def _find_weechat_plugin(self):
    candidates = [
        # 项目级
        os.path.join(project_dir, ".weechat", "python", "autoload", "zchat.py"),
        # XDG（WeeChat 4.x）
        "~/.config/weechat/python/autoload/zchat.py",
        # 传统路径
        "~/.weechat/python/autoload/zchat.py",
    ]
```

> 引用：`zchat/cli/irc_manager.py:302-315`

## 认证系统

### 两种认证模式

1. **OIDC 认证**：`zchat auth login` — 使用 Logto 设备码流程
2. **本地模式**：`zchat auth login --method local --username alice` — 仅设置用户名

### OIDC 设备码流程

```python
# auth.py:135-202
def device_code_flow(issuer, client_id, http_client=None):
    # 1. 发现 OIDC 端点
    endpoints = discover_oidc_endpoints(issuer)
    
    # 2. 请求设备码
    resp = client.post(endpoints["device_authorization_endpoint"], data={
        "client_id": client_id,
        "scope": "openid profile email",
    })
    device_code = resp.json()["device_code"]
    verification_uri = resp.json()["verification_uri_complete"]
    
    # 3. 显示 QR 码
    _print_qr(verification_uri)
    print(f"Open: {verification_uri}")
    
    # 4. 轮询 token 端点
    while True:
        resp = client.post(endpoints["token_endpoint"], data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": client_id,
        })
        if resp.json().get("access_token"):
            break
        time.sleep(interval)
    
    # 5. 获取用户信息
    userinfo = client.get(endpoints["userinfo_endpoint"],
                          headers={"Authorization": f"Bearer {token}"})
    
    # 6. 保存 token
    return {
        "access_token": token,
        "refresh_token": refresh,
        "username": _extract_username(userinfo),
        "email": email,
        "expires_at": time.time() + expires_in,
        ...
    }
```

> 引用：`zchat/cli/auth.py:135-202`

### 用户名提取

```python
# auth.py:118-132
def _extract_username(userinfo):
    # 优先级：username > preferred_username > email 本地部分 > sub
    for field in ["username", "preferred_username"]:
        if userinfo.get(field):
            return _sanitize_irc_nick(userinfo[field])
    if userinfo.get("email"):
        return _sanitize_irc_nick(userinfo["email"].split("@")[0])
    return _sanitize_irc_nick(userinfo.get("sub", "user"))
```

> 引用：`zchat/cli/auth.py:118-132`

### IRC 昵称清理

```python
# auth.py:104-115
def _sanitize_irc_nick(raw):
    # 只保留 RFC 2812 允许的字符
    cleaned = re.sub(r'[^a-zA-Z0-9\-_\\\[\]{}^|]', '', raw)
    # 开头不能是数字或横线
    cleaned = cleaned.lstrip('0123456789-')
    return cleaned or "user"
```

> 引用：`zchat/cli/auth.py:104-115`

### Token 存储

```python
# auth.py:47-53
def save_token(base_dir, token_data):
    path = os.path.join(base_dir, "auth.json")
    with open(path, "w") as f:
        json.dump(token_data, f)
    os.chmod(path, 0o600)  # 只有 owner 可读写
```

存储位置：`~/.zchat/auth.json`，权限 0600。

> 引用：`zchat/cli/auth.py:47-53`

### get_username() — 最常用的函数

```python
# auth.py:18-44
def get_username(base_dir=None):
    auth_path = os.path.join(base_dir, "auth.json")
    if not os.path.isfile(auth_path):
        raise RuntimeError("No username configured. Run: zchat auth login ...")
    
    data = json.load(open(auth_path))
    return data.get("username", "")
```

**几乎所有 CLI 命令都调用这个函数**来获取当前用户名，用于 agent 命名的 scoped_name()。

> 引用：`zchat/cli/auth.py:18-44`

## ergo SASL 认证脚本

当 OIDC 认证启用时，ergo 会调用 `ergo_auth_script.py` 验证 IRC 连接的 SASL 凭证：

```python
# ergo_auth_script.py:25-73
def validate_credentials(account_name, passphrase, userinfo_url):
    # 1. 用 passphrase（即 access_token）调用 userinfo 端点
    resp = httpx.get(userinfo_url, headers={"Authorization": f"Bearer {passphrase}"})
    
    # 2. 提取用户名
    username = _extract_username(resp.json())
    
    # 3. 验证 agent 所有权
    if "-" in account_name:  # scoped agent name
        owner = account_name.split("-", 1)[0]
        if owner != username:
            return {"success": False, "error": "agent owner mismatch"}
    
    return {"success": True, "accountName": account_name}
```

这保证了 `alice-agent0` 只能由 alice 的 token 创建，防止冒名。

> 引用：`zchat/cli/ergo_auth_script.py:25-73`

## 环境检查（doctor）

```python
# doctor.py:70-129
def run_doctor():
    # 必需：tmux, claude, zchat-channel
    # 可选：ergo, weechat, weechat 插件
    # 列出项目和活动项目
    # 输出 ✓/✗ 状态
```

运行 `zchat doctor` 检查所有依赖是否就绪。

> 引用：`zchat/cli/doctor.py:70-129`

## 测试

```bash
uv run pytest tests/unit/test_auth.py -v
```

覆盖：token 保存/加载、过期检测、OIDC 发现、设备码流程。

> 引用：`tests/unit/test_auth.py`

## 下一步

进入 [第七章：WeeChat 插件](./07-weechat-plugin.md)。
