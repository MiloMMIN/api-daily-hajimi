# api.gemai.cc 多账号自动签到（Python + Playwright）

基于 Playwright 的浏览器自动化脚本：依次登录多个账号，执行签到动作，并在结束后退出登录。适用于 SPA 页面场景。

## 功能
- 多账号轮询：从 `accounts.json` 读取账号列表并逐个执行
- 自动化流程：登录 → 进入控制台/个人中心 → 尝试点击“签到” → 退出登录
- 失败留痕：异常时保存截图 `error_<username>.png`
- 风控友好：账号之间默认等待 3 秒

## 目录
- `main.py`：主脚本（Playwright 异步 API）
- `accounts.json`：账号配置（请勿提交到公开仓库）
- `requirements.txt`：Python 依赖

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

## 账号配置
`accounts.json` 为数组，每个元素包含 `username` 与 `password`：

```json
[
  { "username": "your_username_or_email", "password": "your_password" }
]
```

建议把真实账号文件排除在版本控制之外，避免泄露。

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
