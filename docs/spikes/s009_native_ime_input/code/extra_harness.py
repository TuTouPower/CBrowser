import asyncio
import json
import logging
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('extra_harness')

def remote_value():
    code = '''import asyncio,json,urllib.request,websockets,sys
async def main():
 tabs=json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
 tab=next(t for t in tabs if t.get('type')=='page')
 async with websockets.connect(tab['webSocketDebuggerUrl']) as ws:
  await ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':'document.getElementById("spike-input").value','returnByValue':True}}))
  while True:
   r=json.loads(await ws.recv())
   if r.get('id')==1:
    sys.stdout.write(json.dumps(r['result']['result']['value']));return
asyncio.run(main())'''
    r = subprocess.run(['docker','exec','cbrowser-spike-ime-browser','python3','-c',code],capture_output=True,text=True,check=True)
    return json.loads(r.stdout)

async def clear_input(page):
    await page.locator('#overlayInput').focus()
    await page.keyboard.press('Control+a')
    await page.keyboard.press('Backspace')
    await asyncio.sleep(0.5)

async def main():
    sentinel = 'CBROWSER_EXTRA_HARNESS_SENTINEL_20261027'
    subprocess.run(['docker','exec','-i','-e','DISPLAY=:99','cbrowser-spike-ime-browser','xclip','-selection','clipboard','-in'],input=sentinel,text=True,check=True)
    
    results = {}
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(ROOT / 'chrome_profile_extra'),
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            headless=True,
            viewport={'width': 1280, 'height': 720},
            args=['--autoplay-policy=no-user-gesture-required', '--no-first-run']
        )
        page = await ctx.new_page()
        await page.add_init_script('''(() => {
            window.__imeEvents = [];
            window.__imeSends = [];
            window.__pcs = [];
            const P = window.RTCPeerConnection;
            window.RTCPeerConnection = function(...a) {
                const pc = new P(...a);
                window.__pcs.push(pc);
                return pc;
            };
            window.RTCPeerConnection.prototype = P.prototype;
            for (const t of ['compositionstart', 'compositionupdate', 'compositionend', 'input', 'textInput']) {
                document.addEventListener(t, e => window.__imeEvents.push({type: e.type, trusted: e.isTrusted, data: e.data, target: e.target ? e.target.id : null}), true);
            }
            const orig = RTCDataChannel.prototype.send;
            RTCDataChannel.prototype.send = function(data) {
                window.__imeSends.push({label: this.label, data});
                return orig.call(this, data);
            };
        })()''')

        await page.goto('http://127.0.0.1:18095')
        await page.wait_for_function("window.__pcs.some(pc => pc.connectionState === 'connected') && window.webrtcInput", timeout=60000)
        await asyncio.sleep(2)
        await page.mouse.click(640, 360)
        await asyncio.sleep(0.5)

        cdp = await ctx.new_cdp_session(page)

        # 1. Clear initial state
        await clear_input(page)
        assert remote_value() == '', 'Initial clear failed'
        log.info('Initial state clean')

        # 2. Case: Punctuation + CJK ("你好，世界！")
        log.info('Testing Case: Punctuation + CJK')
        await page.locator('#overlayInput').focus()
        await cdp.send('Input.imeSetComposition', {'text': 'nihao', 'selectionStart': 5, 'selectionEnd': 5})
        await asyncio.sleep(0.2)
        await cdp.send('Input.insertText', {'text': '你好，世界！'})
        await asyncio.sleep(2)
        val_punct = remote_value()
        log.info('Punctuation result remote_value: %s', val_punct)
        results['cjk_punctuation'] = {
            'expected': '你好，世界！',
            'actual': val_punct,
            'match': val_punct == '你好，世界！'
        }

        # Clear
        await clear_input(page)
        assert remote_value() == '', 'Clear after punct failed'

        # 3. Case: Cancellation (preedit typed then aborted without commit)
        log.info('Testing Case: Input Cancellation')
        await page.locator('#overlayInput').focus()
        await cdp.send('Input.imeSetComposition', {'text': 'chexiao', 'selectionStart': 7, 'selectionEnd': 7})
        await asyncio.sleep(0.5)
        preedit_remote = remote_value()
        log.info('Preedit on remote during composition: %s', preedit_remote)
        # Cancel composition by clearing composition text
        await cdp.send('Input.imeSetComposition', {'text': '', 'selectionStart': 0, 'selectionEnd': 0})
        await asyncio.sleep(1.5)
        val_cancel = remote_value()
        log.info('Remote value after cancellation: "%s"', val_cancel)
        results['cancellation'] = {
            'preedit_streamed': preedit_remote == 'chexiao',
            'post_cancel_empty': val_cancel == '',
            'actual': val_cancel
        }

        # Clear
        await clear_input(page)

        # 4. Case: Emoji commit ("🎉🚀")
        log.info('Testing Case: Emoji commit')
        await page.locator('#overlayInput').focus()
        await cdp.send('Input.imeSetComposition', {'text': 'emoji', 'selectionStart': 5, 'selectionEnd': 5})
        await asyncio.sleep(0.2)
        await cdp.send('Input.insertText', {'text': '🎉🚀'})
        await asyncio.sleep(2)
        val_emoji = remote_value()
        log.info('Emoji result remote_value: %s', val_emoji)
        results['emoji'] = {
            'expected': '🎉🚀',
            'actual': val_emoji,
            'match': val_emoji == '🎉🚀'
        }

        # Verify container clipboard
        clipboard = subprocess.run(['docker', 'exec', '-e', 'DISPLAY=:99', 'cbrowser-spike-ime-browser', 'xclip', '-selection', 'clipboard', '-out'], capture_output=True, text=True, check=True).stdout
        assert clipboard == sentinel, f'Clipboard corrupted! Expected {sentinel}, got {clipboard}'
        results['clipboard_unmodified'] = True
        log.info('Container clipboard strictly unchanged throughout all harness cases')

        (ROOT / 'extra_harness_result.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
        await ctx.close()

if __name__ == '__main__':
    asyncio.run(main())
