import asyncio
import json
import os
import re
import sys
import subprocess
import urllib.request
from datetime import datetime, timedelta

# 配置信息
BASE_URL = "https://api.gemai.cc"
LOGIN_URL = f"{BASE_URL}/login"
PERSONAL_URL = f"{BASE_URL}/console/personal"
TOPUP_URL = f"{BASE_URL}/console/topup"

def get_webhook_config(config: dict):
    webhook_cfg = (config or {}).get("webhook", {}) or {}
    enabled = webhook_cfg.get("enabled", True)
    url = webhook_cfg.get("url")

    if os.getenv("WECHAT_WEBHOOK_ENABLED") is not None:
        enabled = os.getenv("WECHAT_WEBHOOK_ENABLED", "1") != "0"
    if os.getenv("WECHAT_WEBHOOK_URL"):
        url = os.getenv("WECHAT_WEBHOOK_URL")

    dry_run = os.getenv("WECHAT_WEBHOOK_DRY_RUN", "0") == "1"
    return {"enabled": bool(enabled), "url": url, "dry_run": dry_run}

async def send_wechat_webhook(content: str, webhook_config: dict):
    if not (webhook_config or {}).get("enabled", True):
        return {"ok": False, "disabled": True}

    webhook_url = (webhook_config or {}).get("url")
    if not webhook_url:
        return {"ok": False, "disabled": True}

    payload = {"msgtype": "text", "text": {"content": content}}

    if (webhook_config or {}).get("dry_run"):
        print(f"[webhook dry-run]\n{content}")
        return {"ok": True, "dry_run": True}

    def _post():
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")

    try:
        body = await asyncio.to_thread(_post)
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}

        errcode = parsed.get("errcode")
        if errcode == 0:
            return {"ok": True, "response": parsed}
        return {"ok": False, "response": parsed}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def format_final_report(results):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    success_count = sum(1 for r in results if r.get("ok"))
    failed_count = total - success_count

    lines = [
        "[api-daily] 执行完成",
        f"时间: {ts}",
        f"总计: {total}",
        f"成功: {success_count}",
        f"失败: {failed_count}",
        "",
        "详情:",
    ]

    for r in results:
        username = r.get("username") or "<empty>"
        ok = bool(r.get("ok"))
        status = "成功" if ok else "失败"
        detail = (r.get("detail") or "-").replace("\r", " ").replace("\n", " ").strip()
        
        stats = r.get("stats")
        if stats and isinstance(stats, dict) and not stats.get("error"):
            b = stats.get("balance", "N/A")
            c = stats.get("consumption", "N/A")
            req = stats.get("requests", "N/A")
            detail += f" [统计: 余额{b} / 消耗{c} / 请求{req}]"

        lines.append(f"- {status} | {username} | {detail}")

    return "\n".join(lines)

def load_config():
    defaults = {
        "schedule": {
            "enabled": True,
            "run_immediately_on_start": True,
            "mode": "interval",
            "interval_seconds": 86400,
            "time_of_day": "03:30",
        },
        "browser": {
            "headless": True,
            "launch_timeout_ms": 60000,
            "action_timeout_ms": 30000,
            "navigation_timeout_ms": 45000,
            "locale": "zh-CN",
            "timezone_id": os.getenv("TZ"),
            "debug_network": False,
            "proxy": None,
        },
        "run": {
            "between_accounts_seconds": 2,
            "max_retries": 3,
            "retry_delay_seconds": 300,
        },
    }

    def load_json_with_optional_comments(file_path: str):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            return None

        lines = []
        for line in raw.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("//") or stripped.startswith("#"):
                continue
            lines.append(line)
        filtered = "\n".join(lines).strip()
        if not filtered:
            return {}

        try:
            return json.loads(filtered) or {}
        except Exception:
            return None

    user_cfg = None
    if os.path.exists("config.json"):
        user_cfg = load_json_with_optional_comments("config.json")
    if user_cfg is None and os.path.exists("config.jsonc"):
        user_cfg = load_json_with_optional_comments("config.jsonc")
    if user_cfg is None:
        return defaults

    def deep_merge(base, override):
        if not isinstance(base, dict) or not isinstance(override, dict):
            return override
        merged = dict(base)
        for k, v in override.items():
            if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
                merged[k] = deep_merge(merged[k], v)
            else:
                merged[k] = v
        return merged

    return deep_merge(defaults, user_cfg)

def compute_next_run_at(now: datetime, schedule_cfg: dict):
    mode = (schedule_cfg or {}).get("mode", "interval")
    if mode == "time_of_day":
        time_of_day = (schedule_cfg or {}).get("time_of_day", "03:30")
        try:
            hour_str, minute_str = str(time_of_day).split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
        except Exception:
            hour, minute = 3, 30

        next_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_at <= now:
            next_at = next_at + timedelta(days=1)
        return next_at

    interval_seconds = (schedule_cfg or {}).get("interval_seconds", 86400)
    try:
        interval_seconds = int(interval_seconds)
    except Exception:
        interval_seconds = 86400
    if interval_seconds < 1:
        interval_seconds = 1
    return now + timedelta(seconds=interval_seconds)

def get_chromium_launch_args():
    args = []

    is_linux = os.name == "posix"
    is_docker = False
    try:
        is_docker = os.path.exists("/.dockerenv")
    except Exception:
        is_docker = False

    if is_linux:
        args.append("--disable-dev-shm-usage")

        try:
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                args.append("--no-sandbox")
        except Exception:
            pass

        if is_docker:
            args.append("--disable-gpu")

    return args

def _safe_filename_part(value: str):
    s = (value or "").strip()
    if not s:
        return "empty"
    s = re.sub(r"[^\w\.\-@]+", "_", s, flags=re.UNICODE)
    return s[:80] if len(s) > 80 else s

def _ensure_dir(path: str):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass

def _parse_proxy(proxy_cfg):
    if not proxy_cfg:
        return None
    if isinstance(proxy_cfg, str):
        return {"server": proxy_cfg}
    if isinstance(proxy_cfg, dict):
        server = proxy_cfg.get("server")
        if not server:
            return None
        parsed = {"server": server}
        if proxy_cfg.get("username"):
            parsed["username"] = str(proxy_cfg.get("username"))
        if proxy_cfg.get("password"):
            parsed["password"] = str(proxy_cfg.get("password"))
        return parsed
    return None

async def run_sign_in(account, config: dict):
    username = account.get("username")
    password = account.get("password")
    if not username or not password:
        return {"ok": False, "username": username, "detail": "账号或密码为空，请检查 accounts.json"}
    
    browser_cfg = (config or {}).get("browser", {}) or {}
    headless = browser_cfg.get("headless", True)
    proxy = _parse_proxy(browser_cfg.get("proxy"))
    launch_timeout_ms = browser_cfg.get("launch_timeout_ms", 60000)
    action_timeout_ms = browser_cfg.get("action_timeout_ms", 30000)
    navigation_timeout_ms = browser_cfg.get("navigation_timeout_ms", 45000)
    locale = browser_cfg.get("locale", "zh-CN")
    timezone_id = browser_cfg.get("timezone_id", os.getenv("TZ"))
    debug_network = bool(browser_cfg.get("debug_network", False))
    try:
        launch_timeout_ms = int(launch_timeout_ms)
    except Exception:
        launch_timeout_ms = 60000
    try:
        action_timeout_ms = int(action_timeout_ms)
    except Exception:
        action_timeout_ms = 30000
    try:
        navigation_timeout_ms = int(navigation_timeout_ms)
    except Exception:
        navigation_timeout_ms = 45000

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # 启动浏览器
        # 使用 headless=True 以便在无界面环境下运行
        browser = await p.chromium.launch(
            headless=bool(headless),
            args=get_chromium_launch_args(),
            timeout=launch_timeout_ms,
            proxy=proxy,
        )
        context_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        if locale:
            context_kwargs["locale"] = str(locale)
        if timezone_id:
            context_kwargs["timezone_id"] = str(timezone_id)

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        page.set_default_timeout(action_timeout_ms)
        page.set_default_navigation_timeout(navigation_timeout_ms)
        
        ok = False
        detail = ""
        stats = {}

        artifacts_dir = "artifacts"
        _ensure_dir(artifacts_dir)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name_part = _safe_filename_part(username)
        network_log_path = os.path.join(artifacts_dir, f"{ts}_{name_part}_network.log")
        network_events = []

        def append_network_event(kind: str, message: str):
            if not debug_network:
                return
            try:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                network_events.append(f"{now_str} {kind} {message}")
            except Exception:
                pass

        def flush_network_log():
            if not debug_network:
                return None
            try:
                content = "\n".join(network_events)
                with open(network_log_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return network_log_path
            except Exception:
                return None

        if debug_network:
            page.on("console", lambda msg: append_network_event("console", f"{msg.type} {msg.text}"))
            page.on("pageerror", lambda exc: append_network_event("pageerror", str(exc)))
            page.on("requestfailed", lambda req: append_network_event("requestfailed", f"{req.method} {req.url} {req.failure}"))
            page.on(
                "response",
                lambda res: append_network_event(
                    "response",
                    f"{res.status} {res.request.method} {res.url}",
                )
                if ("/api/" in res.url or "/login" in res.url or "/console" in res.url)
                else None,
            )

        async def dump_artifacts(tag: str):
            tag_part = _safe_filename_part(tag)
            png_path = os.path.join(artifacts_dir, f"{ts}_{name_part}_{tag_part}.png")
            html_path = os.path.join(artifacts_dir, f"{ts}_{name_part}_{tag_part}.html")
            try:
                await page.screenshot(path=png_path, full_page=True)
            except Exception:
                pass
            try:
                html = await page.content()
                await asyncio.to_thread(lambda: open(html_path, "w", encoding="utf-8").write(html))
            except Exception:
                pass
            log_path = flush_network_log()
            return {"png": png_path, "html": html_path, "log": log_path, "url": getattr(page, "url", "")}

        try:
            print(f"正在尝试登录账号: {username}...")
            await page.goto(LOGIN_URL)
            
            # 等待登录表单加载
            await page.wait_for_selector("input[name='username']", timeout=10000)
            
            # 输入账号密码
            await page.fill("input[name='username']", username)
            await page.fill("input[name='password']", password)
            
            # 检查并勾选用户协议（如果有）
            checkbox = page.locator("input[type='checkbox']").first
            label = page.locator("text=我已阅读并同意").first
            
            try:
                # 策略1: 查找 input[type='checkbox']
                if await checkbox.count() > 0:
                    if not await checkbox.is_checked():
                        print("检测到协议复选框，正在强制勾选...")
                        await checkbox.check(force=True)
                        # 补充：尝试触发 click 事件，某些框架可能监听 click 而不是 change
                        # 针对 Semi UI 等框架，尝试点击 checkbox 的父级容器或视觉元素
                        try:
                            if not await checkbox.is_checked():
                                # 尝试点击 Semi UI 的视觉元素
                                semi_inner = page.locator(".semi-checkbox-inner").first
                                if await semi_inner.is_visible():
                                    await semi_inner.click()
                                else:
                                    await checkbox.click(force=True)
                        except Exception:
                            pass
                        await asyncio.sleep(0.5)

                # 策略2: 点击 "我已阅读并同意" 文本
                # 双重保险：如果策略1没生效（例如自定义组件未绑定 input），点击文本通常能触发 toggle
                label = page.locator("text=我已阅读并同意").first
                if await label.is_visible():
                    # 检查 checkbox 是否已勾选（如果能找到的话）
                    if await checkbox.count() == 0 or not await checkbox.is_checked():
                        print("尝试点击协议文本以确保勾选...")
                        await label.click(force=True)
                        await asyncio.sleep(0.5)
            except Exception as e:
                print(f"勾选协议尝试时忽略错误: {e}")

            async def click_login_button():
                # 优先寻找表单内的提交按钮，避免点击到 Header 栏的 "登录" 链接
                candidates = [
                    # 1. 明确的提交按钮
                    "button[type='submit']",
                    # 2. 表单内的按钮
                    "form button:has-text('登录')",
                    "form button:has-text('Continue')",
                    "form button:has-text('继续')",
                    # 3. 排除 Header/Nav 的按钮
                    # 使用 :not(header *) 排除 header 内的按钮
                    "button:not(header *):not(nav *):has-text('登录')",
                    "button:not(header *):not(nav *):has-text('Continue')",
                    "button:not(header *):not(nav *):has-text('继续')",
                    # 4. 原有的一般性策略 (作为最后的兜底，但排除 borderless)
                    "button:not([class*='borderless']):has-text('登录')",
                    "button:not([class*='borderless']):has-text('Sign in')",
                    "button:not([class*='borderless']):has-text('Continue')",
                    "button:not([class*='borderless']):has-text('继续')",
                ]

                for selector in candidates:
                    try:
                        # 查找所有匹配的元素
                        locs = await page.locator(selector).all()
                        
                        for loc in locs:
                            if await loc.is_visible():
                                # 检查是否被禁用（通常是因为未勾选协议）
                                if await loc.is_disabled():
                                    print(f"发现登录按钮 ({selector}) 但被禁用，尝试再次勾选协议...")
                                    
                                    # 针对 Semi UI 的再次尝试
                                    # 先尝试点击 label（通常比较稳妥）
                                    if await label.is_visible():
                                        await label.click(force=True)
                                        await asyncio.sleep(0.5)

                                    if await loc.is_disabled():
                                        # 如果还不行，尝试点击 Semi UI 的 checkbox 视觉元素
                                        semi_inner = page.locator(".semi-checkbox-inner").first
                                        if await semi_inner.is_visible():
                                            await semi_inner.click(force=True)
                                            await asyncio.sleep(0.5)
                                
                                # 再次检查禁用状态
                                if await loc.is_disabled():
                                    print(f"登录按钮 ({selector}) 仍然禁用，尝试下一个...")
                                    continue

                                print(f"尝试点击登录按钮: {selector}")
                                await loc.click(timeout=5000)
                                return {"ok": True, "selector": selector}
                    except Exception:
                        continue
                
                # 如果上面的都失败了，尝试盲点 Enter
                try:
                    await page.press("input[name='password']", "Enter")
                    return {"ok": True, "selector": "press_enter"}
                except Exception:
                    pass

                return {"ok": False, "selector": None}

            click_result = await click_login_button()
            if not click_result.get("ok"):
                artifacts = await dump_artifacts("login_button_missing")
                raise RuntimeError(f"未找到可点击的登录按钮（可能页面结构变化/风控/人机验证）。{artifacts}")
            
            # 等待不再是登录页（因为登录后可能停留在任意页面）
            try:
                await page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
            except Exception:
                print(f"等待跳转超时，当前 URL: {page.url}")
                if "/login" in page.url:
                    # 尝试获取页面上的错误提示信息
                    page_text = ""
                    try:
                        # 获取 body 文本，限制长度
                        body_text = await page.evaluate("document.body.innerText")
                        page_text = (body_text or "").strip()[:500].replace("\n", " ")
                    except Exception:
                        pass
                    
                    artifacts = await dump_artifacts("login_stuck")
                    raise RuntimeError(f"登录后停留在登录页，可能登录失败。页面部分内容: [{page_text}] {artifacts}")
            
            # 尝试关闭系统公告弹窗
            try:
                # 常见的弹窗关闭按钮选择器
                close_selectors = [
                    "button[aria-label='Close']",
                    "button.ant-modal-close",
                    # Semi UI 弹窗关闭按钮
                    "button.semi-modal-close",
                    "button.semi-button[aria-label='关闭']",
                    # 通用
                    "button:has-text('我知道了')",
                    "button:has-text('关闭')", 
                    ".dialog-close"
                ]
                for sel in close_selectors:
                    # 使用 or_ 组合多个定位器可能会比较慢，这里简单循环检测
                    # 设置较短的 timeout，避免浪费时间
                    if await page.locator(sel).first.is_visible(timeout=2000):
                        print(f"检测到弹窗，尝试关闭 ({sel})...")
                        await page.locator(sel).first.click()
                        await asyncio.sleep(0.5)
            except Exception:
                pass
            
            # 直接前往个人中心（签到功能所在页）
            print(f"前往个人中心签到页面...")
            await page.goto(PERSONAL_URL)

            if "/login" in page.url:
                artifacts = await dump_artifacts("redirected_to_login")
                raise RuntimeError(f"访问个人中心被重定向到登录页，疑似未登录成功/被风控。{artifacts}")
            
            # 等待签到按钮出现
            # 按钮可能显示 '每日签到' 或 '今日已签到'
            try:
                checkin_selector = "button:has-text('签到')"
                await page.wait_for_selector(checkin_selector, timeout=10000)
                checkin_btn = page.locator(checkin_selector).first
                
                button_text = await checkin_btn.inner_text()
                if "已签到" in button_text or await checkin_btn.is_disabled():
                    print(f"账号 {username}: 今日已签到 (按钮状态: {button_text})")
                    ok = True
                    detail = f"今日已签到（按钮：{button_text.strip()}）"
                else:
                    await checkin_btn.click()
                    print(f"账号 {username}: 签到成功！")
                    # 等待一下结果显示
                    await page.wait_for_timeout(3000)
                    ok = True
                    detail = "已执行签到点击"
            except Exception as e:
                print(f"账号 {username}: 未能找到签到按钮或执行失败。错误: {str(e)}")
                ok = False
                artifacts = await dump_artifacts("checkin_failed")
                detail = f"未找到签到按钮或执行失败：{str(e)}。{artifacts}"
            
            # 获取账户统计信息
            try:
                print(f"前往充值页面获取账户统计信息...")
                await page.goto(TOPUP_URL)
                # 等待页面加载
                await page.wait_for_selector("text=账户统计", timeout=15000)
                await page.wait_for_timeout(3000) # 等待AJAX数据加载完成

                async def get_stat(label):
                    try:
                        # 查找包含特定文本的元素
                        # 使用 exact=True 避免匹配到其他包含该词的文本
                        el = page.get_by_text(label, exact=True).first
                        
                        # 增加重试等待，防止元素虽然渲染了但内容还在加载
                        for _ in range(3):
                            if await el.is_visible():
                                break
                            await asyncio.sleep(1)
                            
                        if not await el.is_visible():
                            print(f"未找到可见的标签: {label}")
                            return "N/A"

                        # 尝试向上查找父级容器，直到找到包含数值的层级
                        # 通常结构是：容器 -> [数值, 标签] 或 容器 -> [子容器(数值), 子容器(标签)]
                        current = el
                        for i in range(4): # 增加向上查找层级
                            parent = current.locator("..")
                            text = await parent.inner_text()
                            # 简单的文本处理：按行分割，排除掉标签本身
                            lines = [line.strip() for line in text.splitlines() if line.strip()]
                            
                            # 过滤掉标签文本
                            values = [l for l in lines if label not in l]
                            
                            # 简单的数值检查：如果包含 ¥ 或 数字，更有可能是目标值
                            for v in values:
                                if "¥" in v or re.search(r'\d', v):
                                    return v
                            
                            # 如果还没有找到，继续往上
                            current = parent
                        
                        return "N/A"
                    except Exception as e:
                        print(f"获取 {label} 失败: {e}")
                        return "N/A"

                stats["balance"] = await get_stat("当前余额")
                stats["consumption"] = await get_stat("历史消耗")
                stats["requests"] = await get_stat("请求次数")
                print(f"统计获取成功: {stats}")
            except Exception as e:
                print(f"获取账户统计失败: {e}")
                # 不影响整体任务状态，仅记录错误
                stats["error"] = str(e)

            # 由于每个账号都会关闭浏览器并开启新实例，因此无需执行复杂的退出逻辑
            print(f"账号 {username} 任务处理完毕。")
            
        except Exception as e:
            print(f"账号 {username} 执行过程中出错: {str(e)}")
            ok = False
            detail = str(e)
        finally:
            flush_network_log()
            await browser.close()

        return {"ok": ok, "username": username, "detail": detail, "stats": stats}

async def run_once(config: dict):
    if not os.path.exists("accounts.json"):
        print("错误: 未找到 accounts.json 配置文件。")
        return []
        
    with open("accounts.json", "r", encoding="utf-8") as f:
        try:
            accounts = json.load(f)
        except Exception as e:
            print(f"错误: 无法解析 accounts.json。请检查格式。{e}")
            return []
    
    print(f"共发现 {len(accounts)} 个账号，准备开始自动签到任务...")
    
    run_cfg = (config or {}).get("run", {})
    between_accounts_seconds = run_cfg.get("between_accounts_seconds", 2)
    max_retries = run_cfg.get("max_retries", 3)
    retry_delay_seconds = run_cfg.get("retry_delay_seconds", 300)

    try:
        between_accounts_seconds = float(between_accounts_seconds)
    except Exception:
        between_accounts_seconds = 2

    try:
        max_retries = int(max_retries)
        if max_retries < 0: max_retries = 0
    except Exception:
        max_retries = 3

    try:
        retry_delay_seconds = int(retry_delay_seconds)
        if retry_delay_seconds < 0: retry_delay_seconds = 300
    except Exception:
        retry_delay_seconds = 300
    
    final_results = {}
    pending_accounts = list(accounts)

    for attempt in range(max_retries + 1):
        if not pending_accounts:
            break
        
        if attempt > 0:
            print(f"\n[重试机制] 等待 {retry_delay_seconds} 秒后开始第 {attempt}/{max_retries} 次重试...")
            await asyncio.sleep(retry_delay_seconds)
            print(f"开始第 {attempt} 次重试，剩余 {len(pending_accounts)} 个账号...")

        next_pending = []
        for account in pending_accounts:
            username = account.get("username")
            # 已经成功的不再跑
            if final_results.get(username, {}).get("ok"):
                continue

            result = await run_sign_in(account, config)
            
            # 更新结果（覆盖旧的失败结果，或保留新的成功结果）
            final_results[username] = result

            if not result.get("ok"):
                next_pending.append(account)
            
            if between_accounts_seconds > 0:
                await asyncio.sleep(between_accounts_seconds)
        
        pending_accounts = next_pending
        if not pending_accounts:
            print("所有账号均执行成功，无需重试。")
            break

    results = list(final_results.values())
    
    report = format_final_report(results)
    webhook_cfg = get_webhook_config(config)
    webhook_result = await send_wechat_webhook(report, webhook_cfg)
    if not webhook_result.get("ok") and not webhook_result.get("disabled"):
        print(f"Webhook 发送失败: {webhook_result}")

    print("\n所有账号签到任务已完成。")
    return results

import argparse

# ... (Previous imports)

# ... (Functions: get_webhook_config, send_wechat_webhook, format_final_report, load_config, compute_next_run_at, etc.)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true", help="Run the sign-in worker immediately")
    parser.add_argument("--next-run", action="store_true", help="Calculate seconds until next run")
    parser.add_argument("--startup", action="store_true", help="Indicate this is the startup check")
    args = parser.parse_args()

    # 1. Worker 模式：执行具体的签到任务
    if args.worker:
        config = load_config()
        await run_once(config)
        return

    # 2. Next Run 模式：计算下一次运行的等待秒数
    if args.next_run:
        config = load_config()
        schedule_cfg = (config or {}).get("schedule", {})
        
        # 如果未开启调度，返回特殊值（比如 -1 或极大值），让 Shell 脚本决定
        # 这里我们假设未开启调度就只运行一次（在 startup 时），或者永不运行
        if not schedule_cfg.get("enabled", True):
            # 如果是启动时检查，且未开启调度，可能需要运行一次
            # 但通常 enabled=False 意味着完全手动。
            # 这里简单返回一个极大的等待时间，相当于暂停
            print("8640000") 
            return

        # 检查是否需要立即运行
        if args.startup and schedule_cfg.get("run_immediately_on_start", True):
            print("0")
            return

        now = datetime.now()
        next_at = compute_next_run_at(now, schedule_cfg)
        wait_seconds = (next_at - now).total_seconds()
        
        if wait_seconds < 0:
            wait_seconds = 0
            
        print(f"{int(wait_seconds)}")
        return

    # 默认行为：如果什么参数都没传，为了兼容旧习惯，也可以默认运行一次 worker
    # 或者打印帮助
    config = load_config()
    await run_once(config)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
