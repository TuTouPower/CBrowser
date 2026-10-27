import asyncio
import json
import logging
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('ime_probe')


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


async def main():
    sentinel='CBROWSER_IME_PRIVATE_FIXTURE_20261027'
    subprocess.run(['docker','exec','-i','-e','DISPLAY=:99','cbrowser-spike-ime-browser','xclip','-selection','clipboard','-in'],input=sentinel,text=True,check=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(ROOT/'chrome_profile'), executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True, viewport={'width':1280,'height':720}, args=['--autoplay-policy=no-user-gesture-required','--no-first-run'])
        page = await ctx.new_page()
        await page.add_init_script('''(() => {
 window.__SELKIES_STREAMING_MODE__='webrtc';window.__imeEvents=[];window.__imeSends=[];window.__pcs=[];const P=window.RTCPeerConnection;window.RTCPeerConnection=function(...a){const pc=new P(...a);window.__pcs.push(pc);return pc};window.RTCPeerConnection.prototype=P.prototype;
 for(const t of ['compositionstart','compositionupdate','compositionend','input','textInput']) document.addEventListener(t,e=>window.__imeEvents.push({type:e.type,trusted:e.isTrusted,data:e.data,target:e.target.id}),true);
 const orig=RTCDataChannel.prototype.send;
 RTCDataChannel.prototype.send=function(data){window.__imeSends.push({label:this.label,data});return orig.call(this,data)};
})()''')
        await page.goto('http://127.0.0.1:18095')
        await page.wait_for_function("window.__pcs.some(pc=>pc.connectionState==='connected') && window.webrtcInput",timeout=60000)
        await asyncio.sleep(2)
        # UI click establishes official stream focus; remote input is already autofocus.
        await page.mouse.click(640,360)
        await page.keyboard.press('Digit7')
        await asyncio.sleep(.5)
        assert remote_value().endswith('7'), 'ASCII positive control failed'
        await page.keyboard.press('Control+a')
        await page.keyboard.press('Backspace')
        await asyncio.sleep(.5)
        assert remote_value() == '', 'clear failed'
        info = await page.evaluate("() => ({element:window.webrtcInput.element.outerHTML.slice(0,500),assist:!!window.webrtcInput.keyboardInputAssist})")
        log.info('Official input host: %s',info)
        # Focus official desktop overlay input; do not synthesize JS events or mutate values.
        await page.locator('#overlayInput').focus()
        cdp = await ctx.new_cdp_session(page)
        await cdp.send('Input.imeSetComposition',{'text':'zhongwen','selectionStart':8,'selectionEnd':8})
        await asyncio.sleep(.2)
        await cdp.send('Input.insertText',{'text':'中文'})
        await asyncio.sleep(2)
        result = {'remote_value':remote_value(),'events':await page.evaluate('window.__imeEvents'),'sent':await page.evaluate('window.__imeSends')}
        (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        log.info('Native composition observed trusted=%s remoteExact=%s sends=%s',any(e['trusted'] and e['type'].startswith('composition') for e in result['events']),result['remote_value']=='中文',len(result['sent']))
        assert any(e['trusted'] and e['type']=='compositionstart' for e in result['events']), 'No native composition start'
        assert any(e['trusted'] and e['type']=='textInput' and e['data']=='中文' for e in result['events']), 'No native text commit'
        assert any(e['label']=='input' and e['data']=='co,end,中文' for e in result['sent']), 'No official input-channel commit'
        assert result['remote_value']=='中文', 'Native commit not delivered exactly'
        clipboard=subprocess.run(['docker','exec','-e','DISPLAY=:99','cbrowser-spike-ime-browser','xclip','-selection','clipboard','-out'],capture_output=True,text=True,check=True).stdout
        assert clipboard==sentinel, 'Container clipboard changed during composition'
        log.info('Container clipboard sentinel unchanged; host clipboard untouched')
        await ctx.close()

if __name__=='__main__':
    asyncio.run(asyncio.wait_for(main(),100))
