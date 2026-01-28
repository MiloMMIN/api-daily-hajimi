# api.gemai.cc 多账号自动签到（Python + Playwright）

基于 Playwright 的浏览器自动化脚本：依次登录多个账号，执行签到动作，采集账户统计数据，并在结束后退出登录。适用于 SPA 页面场景。

## 功能
- **多账号轮询**：从 `accounts.json` 读取账号列表并逐个执行
- **自动化流程**：登录 → 进入控制台/个人中心 → 尝试点击“签到” → 采集账户数据（余额/消耗/请求数） → 退出登录
- **数据采集**：自动抓取账户余额、历史消耗、请求次数并汇总到通知中
- **失败留痕**：异常时保存截图 `error_<username>.png` 和网络日志
- **风控友好**：账号之间默认等待 2 秒（可配置）
- **运行通知**：可选企业微信机器人 Webhook 推送执行结果（可配置）
- **定时执行**：支持按间隔或每天固定时间自动运行（可配置）
- **低内存模式**：Docker 模式下采用 Shell 脚本调度，空闲时几乎不占用内存

## 目录
- `main.py`：主脚本（Playwright 异步 API）
- `entrypoint.sh`：调度脚本（用于 Docker 环境低内存运行）
- `accounts.json`：账号配置（请勿提交到公开仓库）
- `accounts.example.json`：账号配置模板（可提交）
- `requirements.txt`：Python 依赖
- `config.jsonc`：本地运行配置（支持注释；请勿提交到公开仓库）
- `config.example.jsonc`：带注释的配置模板（可提交）
- `Dockerfile` / `Dockerfile.cn`：容器构建文件

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

本项目的 Docker 镜像经过特殊优化，使用 Shell 脚本作为调度器，在空闲等待时几乎不消耗内存（<1MB），仅在执行任务时启动 Python 进程。

### 1. 构建镜像

**推荐：国内网络加速版**
基于 Docker Hub 的 `python` 镜像，并内置 Playwright 国内下载源：

```bash
docker build -f Dockerfile.cn -t api-daily .
```

或者使用普通版（基于官方 Python 镜像）：

```bash
docker build -t api-daily .
```

### 2. 运行容器

请确保 `accounts.json` 和 `config.jsonc` 已经存在于当前目录。

```bash
docker run -d \
  --name api-daily \
  --ipc=host \
  --restart unless-stopped \
  -e TZ=Asia/Shanghai \
  -v "$(pwd)/accounts.json:/app/accounts.json" \
  -v "$(pwd)/config.jsonc:/app/config.jsonc" \
  -v "$(pwd)/artifacts:/app/artifacts" \
  api-daily
```

**参数说明：**
*   `--ipc=host`: **必须添加**。Chromium 在 Docker 中运行时需要共享内存，否则容易崩溃。
*   `-v .../artifacts:/app/artifacts`: 挂载运行产物目录，方便查看报错截图和日志。
*   `--restart unless-stopped`: 容器退出或重启后自动恢复运行。

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
将 `config.jsonc` 中 `browser.headless` 改为 `false`，即可看到浏览器界面便于定位元素。

## 说明
- 页面若出现强人机验证/风控，可能需要手动处理一次或调整等待与定位逻辑
- 签到按钮定位默认在“个人中心”和“首页”各尝试一次，页面结构变动时需要更新选择器
