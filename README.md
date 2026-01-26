# api.gemai.cc 多账号自动签到（Python + Playwright）

基于 Playwright 的浏览器自动化脚本：依次登录多个账号，执行签到动作，并在结束后退出登录。适用于 SPA 页面场景。

## 功能
- 多账号轮询：从 `accounts.json` 读取账号列表并逐个执行
- 自动化流程：登录 → 进入控制台/个人中心 → 尝试点击“签到” → 退出登录
- 失败留痕：异常时保存截图 `error_<username>.png`
- 风控友好：账号之间默认等待 2 秒（可配置）
- 运行通知：可选企业微信机器人 Webhook 推送执行结果（可配置）
- 定时执行：支持按间隔或每天固定时间自动运行（可配置）

## 目录
- `main.py`：主脚本（Playwright 异步 API）
- `accounts.json`：账号配置（请勿提交到公开仓库）
- `accounts.example.json`：账号配置模板（可提交）
- `requirements.txt`：Python 依赖
- `config.jsonc`：本地运行配置（支持注释；请勿提交到公开仓库）
- `config.example.jsonc`：带注释的配置模板（可提交）
- `Dockerfile`：基础容器构建文件

## 环境要求
- Python 3.8+（建议 3.10+）
- Windows / macOS / Linux 均可

## 快速开始
在项目根目录执行：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

## 配置文件（config.jsonc）
默认会读取 `config.jsonc`（或 `config.json`）。推荐使用 `config.jsonc`，因为可以写注释说明。

### 定时模式
- `schedule.mode="interval"`：按固定间隔执行（使用 `schedule.interval_seconds`，默认 86400 秒 = 1 天）
- `schedule.mode="time_of_day"`：每天固定时间执行（使用 `schedule.time_of_day`，格式 `HH:MM`）
- `schedule.run_immediately_on_start=true`：启动后先立刻跑一次；第二次开始才按定时规则执行
- `schedule.enabled=false`：关闭常驻调度（程序仅运行一次就退出）

### Webhook（企业微信机器人）
在 `config.jsonc` 中配置：

```jsonc
{
  "webhook": {
    "enabled": true,
    "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
  }
}
```

也支持用环境变量覆盖（适合 Docker / 服务器部署）：
- `WECHAT_WEBHOOK_URL`：覆盖 webhook 地址
- `WECHAT_WEBHOOK_ENABLED=0`：关闭发送
- `WECHAT_WEBHOOK_DRY_RUN=1`：仅打印消息，不真实发送

## 账号配置
`accounts.json` 为数组，每个元素包含 `username` 与 `password`：

```json
[
  { "username": "your_username_or_email", "password": "your_password" }
]
```

建议把真实账号文件排除在版本控制之外，避免泄露。

## Docker（服务器运行）
构建镜像：

```bash
docker build -t api-daily:latest .
```

### 国内网络加速（推荐）
如果国内拉取 `mcr.microsoft.com` 很慢，可以改用 `Dockerfile.cn`（基于 Docker Hub 的 `python` 镜像，并内置 Playwright 下载镜像源）：

```bash
docker build -f Dockerfile.cn -t api-daily:cn .
```

后续运行时把镜像名替换为 `api-daily:cn` 即可。

运行（把本地 `accounts.json` 与 `config.jsonc` 挂载到容器内）：

```bash
docker run -d --name api-daily \
  --ipc=host \
  -e TZ=Asia/Shanghai \
  -v "$(pwd)/accounts.json:/app/accounts.json:ro" \
  -v "$(pwd)/config.jsonc:/app/config.jsonc:ro" \
  --restart unless-stopped \
  api-daily:latest
```

## 国内镜像（Playwright 浏览器下载加速）
Playwright 首次使用需要下载浏览器（Chromium/Firefox/WebKit），国内网络可能较慢。可设置镜像下载源：

PowerShell（当前会话临时生效）：

```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright/"
python -m playwright install chromium
```

PowerShell（永久生效，重开终端/重启 VS Code 后生效）：

```powershell
setx PLAYWRIGHT_DOWNLOAD_HOST "https://npmmirror.com/mirrors/playwright/"
```

## 常见问题
### VS Code 显示 exited with code=9009
9009 通常是“命令找不到”（例如 Code Runner 找不到 `python`）。建议：

- 使用终端直接运行：`python main.py`
- 或在 VS Code 里选择解释器：`Python: Select Interpreter`，再使用 “Run Python File”

### Playwright 报 Executable doesn't exist
原因是浏览器未安装/未下载，执行：

```bash
python -m playwright install chromium
```

### 需要调试页面元素
将 `main.py` 中 `headless=True` 改为 `False`，即可看到浏览器界面便于定位元素。

## 说明
- 页面若出现强人机验证/风控，可能需要手动处理一次或调整等待与定位逻辑
- 签到按钮定位默认在“个人中心”和“首页”各尝试一次，页面结构变动时需要更新选择器
