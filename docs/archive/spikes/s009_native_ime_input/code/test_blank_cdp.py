import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(ROOT / 'chrome_profile_blank'),
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            headless=True,
            viewport={'width': 800, 'height': 600},
            args=['--no-first-run']
        )
        page = await ctx.new_page()
        await page.set_content('''<!DOCTYPE html><html><body><input id="test" autofocus /></body></html>''')
        await page.evaluate('''() => {
            window.__events = [];
            for (const t of ['compositionstart', 'compositionupdate', 'compositionend', 'input', 'textInput', 'beforeinput']) {
                document.getElementById('test').addEventListener(t, (e) => {
                    window.__events.push({
                        type: e.type,
                        trusted: e.isTrusted,
                        data: e.data,
                        inputType: e.inputType
                    });
                });
            }
        }''')
        await page.locator('#test').focus()
        cdp = await ctx.new_cdp_session(page)
        
        await cdp.send('Input.imeSetComposition', {'text': 'zhongwen', 'selectionStart': 8, 'selectionEnd': 8})
        await asyncio.sleep(0.1)
        await cdp.send('Input.insertText', {'text': '中文'})
        await asyncio.sleep(0.5)
        
        events = await page.evaluate('window.__events')
        print("BLANK PAGE CDP EVENTS:")
        print(json.dumps(events, ensure_ascii=False, indent=2))
        await ctx.close()

if __name__ == '__main__':
    asyncio.run(main())
