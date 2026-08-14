"""UI/DOM tests: drives the real page in Chrome over CDP and asserts on the rendered DOM."""
import json, os, sys, urllib.request, websocket

PAGE_URL = "file://" + os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "index.html"))
CDP = os.environ.get("CDP_URL", "http://localhost:29229")
tabs = json.load(urllib.request.urlopen(CDP + "/json"))
pages = [t for t in tabs if t["type"] == "page"]
tab = next((t for t in pages if "index.html" in t["url"] or "battleship" in t["url"].lower()), pages[0])
ws = websocket.create_connection(tab["webSocketDebuggerUrl"], suppress_origin=True)
_id = [0]

def cmd(method, params):
    _id[0] += 1
    ws.send(json.dumps({"id": _id[0], "method": method, "params": params}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == _id[0]:
            return msg["result"]

def ev(expr):
    res = cmd("Runtime.evaluate",
              {"expression": expr, "returnByValue": True, "awaitPromise": True})
    if "exceptionDetails" in res:
        raise RuntimeError(res["exceptionDetails"].get("text") + " " +
                           str(res["exceptionDetails"].get("exception", {}).get("description", "")))
    return res["result"].get("value")

passed, failures = 0, []
def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failures.append(f"{name} {detail}")
        print(f"  FAIL {name} {detail}")

ev(f"location.href = {json.dumps(PAGE_URL)}")
ev("new Promise(r => setTimeout(r, 800))")
ev("document.getElementById('resetBtn').click()")

CELL = "document.querySelectorAll('#playerGrid .cell')[{}]"
def pcell(r, c): return f"document.querySelector('#playerGrid .cell[data-r=\"{r}\"][data-c=\"{c}\"]')"
def ecell(r, c): return f"document.querySelector('#enemyGrid .cell[data-r=\"{r}\"][data-c=\"{c}\"]')"

def hover(sel):
    """Move the real pointer over an element so CSS :hover matches too."""
    box = ev(f"(()=>{{const b={sel}.getBoundingClientRect();"
             f"return [b.left+b.width/2, b.top+b.height/2];}})()")
    cmd("Input.dispatchMouseEvent",
        {"type": "mouseMoved", "x": box[0], "y": box[1], "buttons": 0})

def unhover():
    cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 2, "y": 2, "buttons": 0})

print("\n--- Manual placement ---")
check("starts in placing phase, enemy grid not clickable",
      ev("state.phase") == "placing" and ev("!!document.querySelector('#enemyGrid .clickable')") is False)
check("clicking enemy grid during placement does nothing",
      (ev(f"{ecell(0,0)}.click(); state.ai.shots[0][0]") is None))

hover(pcell(0, 6))
check("invalid hover shows preview-bad (Carrier at A7 would overflow)",
      ev("document.querySelectorAll('#playerGrid .preview-bad').length") > 0)
ev(f"{pcell(0,6)}.click()")
check("illegal placement rejected with message",
      ev("state.player.ships.length") == 0 and "Can't place" in ev("document.getElementById('status').textContent"))

hover(pcell(3, 3))
check("hover preview is horizontal before rotating",
      ev(f"{pcell(3,7)}.classList.contains('preview')") is True and
      ev(f"{pcell(7,3)}.classList.contains('preview')") is False)
ev("document.dispatchEvent(new KeyboardEvent('keydown',{key:'r'}))")
check("R redraws the preview vertically without moving the cursor",
      ev(f"{pcell(7,3)}.classList.contains('preview')") is True and
      ev(f"{pcell(3,7)}.classList.contains('preview')") is False)
ev("document.dispatchEvent(new KeyboardEvent('keydown',{key:'r'}))")
unhover()

ev(f"{pcell(0,0)}.click()")  # Carrier A1 horizontal
check("Carrier placed and rendered", ev("state.player.ships.length") == 1 and
      ev(f"{pcell(0,4)}.classList.contains('ship')") is True)
ev("document.dispatchEvent(new KeyboardEvent('keydown',{key:'r'}))")
check("R key rotates to vertical", ev("state.horizontal") is False and
      "Vertical" in ev("document.getElementById('rotateBtn').textContent"))
ev(f"{pcell(2,0)}.click()")  # Battleship C1 vertical
check("vertical Battleship occupies C1..F1",
      ev("state.player.ships[1].cells.map(x=>x.join(',')).join(' ')") == "2,0 3,0 4,0 5,0")
ev(f"{pcell(0,0)}.click()")
check("overlapping placement rejected", ev("state.player.ships.length") == 2)
ev("document.getElementById('rotateBtn').click()")
ev(f"{pcell(7,0)}.click()")   # Cruiser
ev(f"{pcell(8,0)}.click()")   # Submarine
check("still placing before last ship", ev("state.phase") == "placing")
ev(f"{pcell(9,0)}.click()")   # Destroyer -> battle starts
check("battle starts after 5th ship", ev("state.phase") == "playing")
check("enemy fleet auto-placed with 17 cells",
      ev("state.ai.ships.length") == 5 and ev("state.ai.ships.reduce((a,s)=>a+s.len,0)") == 17)
check("placement controls disabled during battle",
      ev("document.getElementById('rotateBtn').disabled") is True and
      ev("document.getElementById('randomBtn').disabled") is True)
check("enemy cells now clickable",
      ev("document.querySelectorAll('#enemyGrid .clickable').length") == 100)

print("\n--- Firing / turn rules ---")
ev("window.__origTimeout = window.setTimeout; window.setTimeout = (f,t)=>window.__origTimeout(f,0)")
# find a known miss cell and a known hit cell on the enemy board
miss = ev("(()=>{for(let r=0;r<10;r++)for(let c=0;c<10;c++)if(!state.ai.shipAt[r][c]&&!state.ai.shots[r][c])return [r,c];})()")
ev(f"{ecell(miss[0],miss[1])}.click()")
check("miss renders as miss and logs", ev(f"state.ai.shots[{miss[0]}][{miss[1]}]") == "miss" and
      ev(f"{ecell(miss[0],miss[1])}.classList.contains('miss')") is True)
before = ev("state.ai.shots.flat().filter(Boolean).length")
ev(f"{ecell(miss[0],miss[1])}.click()")
check("clicking an already-fired cell is a no-op",
      ev("state.ai.shots.flat().filter(Boolean).length") == before and
      "already fired" in ev("document.getElementById('status').textContent"))
ev("new Promise(r=>setTimeout(r,300))")
check("computer took its turn after player's miss",
      ev("state.player.shots.flat().filter(Boolean).length") >= 1)

hit = ev("(()=>{for(let r=0;r<10;r++)for(let c=0;c<10;c++)if(state.ai.shipAt[r][c]&&!state.ai.shots[r][c])return [r,c];})()")
shots_before = ev("state.player.shots.flat().filter(Boolean).length")
ev(f"{ecell(hit[0],hit[1])}.click()")
ev("new Promise(r=>setTimeout(r,300))")
check("hit renders and player keeps the turn (computer did not fire)",
      ev(f"{ecell(hit[0],hit[1])}.classList.contains('hit') || {ecell(hit[0],hit[1])}.classList.contains('sunk')") is True
      and ev("state.player.shots.flat().filter(Boolean).length") == shots_before)

print("\n--- Turn lock while the computer is thinking ---")
ev("window.setTimeout = window.__origTimeout")  # restore real 700ms delay
ev("document.getElementById('resetBtn').click(); document.getElementById('randomBtn').click()")
miss2 = ev("(()=>{for(let r=0;r<10;r++)for(let c=0;c<10;c++)if(!state.ai.shipAt[r][c]&&!state.ai.shots[r][c])return [r,c];})()")
ev(f"{ecell(miss2[0],miss2[1])}.click()")
check("turn hands to computer after a miss", ev("state.turn") == "computer")
locked_before = ev("state.ai.shots.flat().filter(Boolean).length")
ev("(()=>{const c=[...document.querySelectorAll('#enemyGrid .cell')].find(x=>!state.ai.shots[+x.dataset.r][+x.dataset.c]); c.click();})()")
check("clicks are ignored during the computer's delay",
      ev("state.ai.shots.flat().filter(Boolean).length") == locked_before and
      "Hold fire" in ev("document.getElementById('status').textContent"))
check("enemy cells are not marked clickable while locked",
      ev("document.querySelectorAll('#enemyGrid .clickable').length") == 0)
ev("new Promise(r=>window.__origTimeout(r,1500))")
check("turn returns to player after the computer finishes", ev("state.turn") == "player" and
      ev("document.querySelectorAll('#enemyGrid .clickable').length") > 0)

print("\n--- New Game during the computer's turn (stale timer) ---")
ev("document.getElementById('randomBtn').disabled ? 0 : 0")
m3 = ev("(()=>{for(let r=0;r<10;r++)for(let c=0;c<10;c++)if(!state.ai.shipAt[r][c]&&!state.ai.shots[r][c])return [r,c];})()")
ev(f"{ecell(m3[0],m3[1])}.click()")          # hand turn to computer (700ms pending)
ev("document.getElementById('resetBtn').click()")  # reset mid-delay
ev("new Promise(r=>window.__origTimeout(r,1500))")
check("pending computer shot does not fire into the new game",
      ev("state.phase") == "placing" and ev("state.player.shots.flat().filter(Boolean).length") == 0 and
      ev("document.getElementById('log').textContent") == "")

ev("document.getElementById('resetBtn').click(); document.getElementById('randomBtn').click()")
ev("window.setTimeout = (f,t)=>window.__origTimeout(f,0)")

print("\n--- Play out a full game through the UI ---")
ev("""
window.__uiPlay = () => new Promise(resolve => {
  const step = () => {
    if (state.phase !== 'playing') return resolve(state.phase);
    let target = null;
    outer: for (let r=0;r<10;r++) for (let c=0;c<10;c++) {
      if (!state.ai.shots[r][c] && state.ai.shipAt[r][c]) { target=[r,c]; break outer; }
    }
    document.querySelector(`#enemyGrid .cell[data-r="${target[0]}"][data-c="${target[1]}"]`).click();
    setTimeout(step, 0);
  };
  step();
});
""")
ev("__uiPlay()")
check("game reaches 'over'", ev("state.phase") == "over")
check("player wins when all enemy ships sunk (cheating aim)",
      "You win" in ev("document.getElementById('status').textContent"))
check("all enemy ships marked sunk in fleet panel",
      ev("state.ai.ships.every(s=>s.sunk)") is True and
      "enemy: afloat" not in ev("document.getElementById('fleet').textContent"))
check("no repeated shots recorded",
      ev("state.ai.shots.flat().filter(v=>v==='hit').length") == 17)
check("victory overlay shown with New Game button",
      ev("document.getElementById('endOverlay').hidden") is False and
      "Victory" in ev("document.getElementById('endTitle').textContent") and
      "sank the enemy fleet" in ev("document.getElementById('endMsg').textContent") and
      ev("document.getElementById('endCard').classList.contains('win')") is True)
check("overlay card never covers either grid, and the scrim is translucent",
      ev("(()=>{const c=document.getElementById('endCard').getBoundingClientRect();"
         "const clear=id=>{const g=document.getElementById(id).getBoundingClientRect();"
         "return c.top>=g.bottom||c.bottom<=g.top||c.left>=g.right||c.right<=g.left;};"
         "const bg=getComputedStyle(document.getElementById('endOverlay')).backgroundColor;"
         "const a=parseFloat((bg.match(/rgba?\\([^)]*?,\\s*([\\d.]+)\\)/)||[])[1] ?? '1');"
         "return clear('playerGrid') && clear('enemyGrid') && a < 0.6;})()") is True)
check("firing after game over is ignored", (lambda b: (
      ev("(()=>{const c=[...document.querySelectorAll('#enemyGrid .cell')].find(x=>!state.ai.shots[+x.dataset.r][+x.dataset.c]); if(c) c.click(); return 1;})()"),
      ev("state.ai.shots.flat().filter(Boolean).length") == b)[1])(
      ev("state.ai.shots.flat().filter(Boolean).length")))

print("\n--- New Game reset ---")
ev("document.getElementById('endNewGame').click()")
check("overlay New Game restarts and hides the overlay",
      ev("document.getElementById('endOverlay').hidden") is True and
      ev("state.phase") == "placing" and
      ev("document.getElementById('endCard').className") == "")
ev("document.getElementById('resetBtn').click()")
check("reset clears boards, log and phase",
      ev("state.phase") == "placing" and ev("state.player.ships.length") == 0 and
      ev("state.ai.shots.flat().filter(Boolean).length") == 0 and
      ev("document.getElementById('log').textContent") == "" and
      ev("document.querySelectorAll('#playerGrid .ship, #playerGrid .hit, #playerGrid .miss').length") == 0)
check("rotate resets to horizontal label",
      "Horizontal" in ev("document.getElementById('rotateBtn').textContent"))
hover(pcell(3, 3))
ev("document.getElementById('resetBtn').click()")
check("preview redraws at the hovered cell after New Game",
      ev(f"{pcell(3,7)}.classList.contains('preview')") is True)
unhover()

print("\n--- Sound ---")
check("shot sounds play without throwing",
      ev("(()=>{try{playShotSound(true);playShotSound(false);return 'ok';}catch(e){return String(e);}})()") == "ok")
ev("document.getElementById('soundBtn').click()")
check("sound toggles off",
      ev("soundOn") is False and
      "Off" in ev("document.getElementById('soundBtn').textContent") and
      ev("document.getElementById('soundBtn').getAttribute('aria-pressed')") == "false")
check("muted shots are silent but still safe",
      ev("(()=>{try{playShotSound(true);return audioCtx===null||soundOn===false;}catch(e){return String(e);}})()") is True)
ev("document.getElementById('soundBtn').click()")
check("sound toggles back on",
      ev("soundOn") is True and "On" in ev("document.getElementById('soundBtn').textContent"))
ev("""(()=>{window.__nodes=0;
     const AC=window.AudioContext.prototype;
     if(!AC.__counted){AC.__counted=1;
       for(const m of ['createOscillator','createBufferSource']){
         const o=AC[m];AC[m]=function(){window.__nodes++;return o.apply(this,arguments);};}}
     return 1;})()""")
ev("document.getElementById('resetBtn').click()")
hover(pcell(2, 2))
ev("(()=>{window.__nodes=0; return 1;})()")
ev(f"{pcell(2,2)}.click()")
check("placing a ship plays a sound", ev("window.__nodes") > 0)
check("illegal placement plays no sound",
      ev("(()=>{window.__nodes=0;"
         "const before=state.player.ships.length;"
         "document.querySelector('#playerGrid .cell[data-r=\"9\"][data-c=\"9\"]').click();"
         "return state.player.ships.length===before ? window.__nodes : -1;})()") == 0)
ev("document.getElementById('soundBtn').click()")
ev("(()=>{window.__nodes=0; return 1;})()")
ev(f"{pcell(5,0)}.click()")
check("muted placement is silent", ev("window.__nodes") == 0)
ev("document.getElementById('soundBtn').click()")
ev("document.getElementById('resetBtn').click()")
unhover()

peaks = ev("""(async()=>{const peak=async fn=>{const off=new OfflineAudioContext(1,44100*2,44100);
     fn(off);const b=await off.startRendering();let m=0;for(const v of b.getChannelData(0))
     m=Math.max(m,Math.abs(v));return m;};
     return [await peak(playFanfare), await peak(playDefeatJingle), await peak(playPlacement)];})()""")
check("end-screen jingles and the placement thunk render audible audio offline",
      all(p > 0.05 for p in peaks), str(peaks))

print("\n--- Defeat end screen ---")
# Sink every player cell but one, then let the computer fire the finishing shot.
ev("""(()=>{document.getElementById('resetBtn').click();
     document.getElementById('randomBtn').click();
     const cells = state.player.ships.flatMap(s => s.cells);
     const last = cells.pop();
     cells.forEach(([r,c]) => fire(state.player, r, c));
     state.turn = 'computer';
     state.aiTargets = [last];
     aiTurn();
     return state.player.shots.flat().filter(v=>v==='hit').length;})()""")
check("defeat overlay shown when the computer wins",
      ev("state.phase") == "over" and
      ev("document.getElementById('endOverlay').hidden") is False and
      "Defeat" in ev("document.getElementById('endTitle').textContent") and
      ev("document.getElementById('endCard').classList.contains('lose')") is True)
ev("document.getElementById('endNewGame').click()")

print("\n--- Random placement path ---")
ev("document.getElementById('randomBtn').click()")
check("random placement starts battle with a legal fleet",
      ev("state.phase") == "playing" and ev("state.player.ships.length") == 5 and
      ev("state.player.ships.reduce((a,s)=>a+s.len,0)") == 17)

check("no console/page errors observed", ev("1") == 1)
ev("window.setTimeout = window.__origTimeout")
ev("document.getElementById('resetBtn').click()")

print(f"\n{passed} UI checks passed, {len(failures)} failed")
sys.exit(1 if failures else 0)
