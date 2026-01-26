import asyncio
import json
import os
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright

# 配置信息
BASE_URL = "https://api.gemai.cc"
LOGIN_URL = f"{BASE_URL}/login"
PERSONAL_URL = f"{BASE_URL}/console/personal"
WEBHOOK_URL = os.getenv(
    "WECHAT_WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=78ff6c36-f371-49db-b08f-dd1a08289db3",
)

async def send_wechat_webhook(content: str):
    if os.getenv("WECHAT_WEBHOOK_ENABLED", "1") == "0":
        return {"ok": False, "disabled": True}

    payload = {"msgtype": "text", "text": {"content": content}}

    if os.getenv("WECHAT_WEBHOOK_DRY_RUN", "0") == "1":
        print(f"[webhook dry-run]\n{content}")
        return {"ok": True, "dry_run": True}

    def _post():
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            WEBHOOK_URL,
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
        lines.append(f"- {status} | {username} | {detail}")

    return "\n".join(lines)

async def run_sign_in(account):
    username = account.get("username")
    password = account.get("password")
    if not username or not password:
        return {"ok": False, "username": username, "detail": "账号或密码为空，请检查 accounts.json"}
    
    async with async_playwright() as p:
        # 启动浏览器
        # 使用 headless=True 以便在无界面环境下运行
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        ok = False
        detail = ""

        try:
            print(f"正在尝试登录账号: {username}...")
            await page.goto(LOGIN_URL)
            
            # 等待登录表单加载
            await page.wait_for_selector("input[name='username']", timeout=10000)
            
            # 输入账号密码
            await page.fill("input[name='username']", username)
            await page.fill("input[name='password']", password)
            
            # 点击登录按钮
            # Hajimi API / New API 使用 '继续' 或 '登录'
            login_btn = page.locator("button:has-text('继续'), button:has-text('登录'), button:has-text('登 录')").first
            await login_btn.click()
            
            # 等待进入控制台
            try:
                await page.wait_for_url(lambda url: "/console" in url, timeout=20000)
            except Exception:
                print(f"等待跳转超时，当前 URL: {page.url}")
            
            # 直接前往个人中心（签到功能所在页）
            print(f"前往个人中心签到页面...")
            await page.goto(PERSONAL_URL)
            
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
                detail = f"未找到签到按钮或执行失败：{str(e)}"
            
            # 由于每个账号都会关闭浏览器并开启新实例，因此无需执行复杂的退出逻辑
            print(f"账号 {username} 任务处理完毕。")
            
        except Exception as e:
            print(f"账号 {username} 执行过程中出错: {str(e)}")
            # 截图保存错误现场
            try:
                await page.screenshot(path=f"error_{username}.png")
            except Exception:
                pass
            ok = False
            detail = str(e)
        finally:
            await browser.close()

        return {"ok": ok, "username": username, "detail": detail}

async def main():
    if not os.path.exists("accounts.json"):
        print("错误: 未找到 accounts.json 配置文件。")
        return
        
    with open("accounts.json", "r", encoding="utf-8") as f:
        try:
            accounts = json.load(f)
        except Exception as e:
            print(f"错误: 无法解析 accounts.json。请检查格式。{e}")
            return
    
    print(f"共发现 {len(accounts)} 个账号，准备开始自动签到任务...")
    results = []
    
    for account in accounts:
        result = await run_sign_in(account)
        results.append(result)

        # 账号之间稍微停顿
        await asyncio.sleep(2)
    
    report = format_final_report(results)
    webhook_result = await send_wechat_webhook(report)
    if not webhook_result.get("ok") and not webhook_result.get("disabled"):
        print(f"Webhook 发送失败: {webhook_result}")

    print("\n所有账号签到任务已完成。")

if __name__ == "__main__":
    asyncio.run(main())
