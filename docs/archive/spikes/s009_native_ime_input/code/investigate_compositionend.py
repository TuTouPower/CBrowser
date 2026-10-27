import asyncio
import json
import logging
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('investigate_ime')

async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(ROOT / 'chrome_profile_investigate'),
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            headless=True,
            viewport={'width': 1280, 'height': 720},
            args=['--autoplay-policy=no-user-gesture-required', '--no-first-run']
        )
        page = await ctx.new_page()
        await page.add_init_script('''(() => {
            window.__trace = [];
            const origDispatch = EventTarget.prototype.dispatchEvent;
            EventTarget.prototype.dispatchEvent = function(event) {
                try {
                    window.__trace.push({
                        kind: 'dispatchEvent',
                        type: event.type,
                        target: this.id || this.tagName || String(this),
                        stack: new Error().stack
                    });
                } catch(err) {}
                return origDispatch.apply(this, arguments);
            };

            for (const t of ['compositionstart', 'compositionupdate', 'compositionend', 'input', 'textInput']) {
                document.addEventListener(t, (e) => {
                    window.__trace.push({
                        kind: 'listener',
                        type: e.type,
                        trusted: e.isTrusted,
                        data: e.data,
                        target: e.target ? (e.target.id || e.target.tagName) : null,
                        stack: new Error().stack
                    });
                }, true);
            }
        })()''')

        await page.goto('http://127.0.0.1:18095')
        await page.wait_for_function("window.webrtcInput", timeout=60000)
        await asyncio.sleep(2)

        await page.locator('#overlayInput').focus()
        cdp = await ctx.new_cdp_session(page)
        
        # Test 1: imeSetComposition
        await cdp.send('Input.imeSetComposition', {'text': 'zhongwen', 'selectionStart': 8, 'selectionEnd': 8})
        await asyncio.sleep(0.2)
        
        # Test 2: insertText
        await cdp.send('Input.insertText', {'text': '中文'})
        await asyncio.sleep(1)

        trace = await page.evaluate('window.__trace')
        (ROOT / 'investigate_trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2))
        for item in trace:
            log.info('TRACE: %s', item)

        await ctx.close()

if __name__ == '__main__':
    asyncio.run(main())
