// Test harness for Battleship. Extracts the CORE LOGIC block verbatim from
// index.html so the shipped code (not a copy) is what gets exercised.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const m = html.match(/\/\/ ===== CORE LOGIC START[^\n]*\n([\s\S]*?)\n\/\/ ===== CORE LOGIC END/);
if (!m) throw new Error("core logic block not found in index.html");

// Deterministic PRNG so failures are reproducible.
let seed = 12345;
function rng() {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 4294967296;
}
const sandbox = { Math: Object.create(Math), console };
sandbox.Math.random = rng;
vm.createContext(sandbox);
vm.runInContext(m[1] + "\n;this.API={SIZE,SHIPS,LETTERS,emptyBoard,newState,canPlace,placeShip,randomizeBoard,fire,allSunk,aiChooseShot,aiUpdateTargets,coordName};", sandbox);
const G = sandbox.API;

let passed = 0;
const failures = [];
function check(name, cond, detail) {
  if (cond) { passed++; return; }
  failures.push(detail ? `${name}: ${detail}` : name);
}
function section(t) { console.log(`\n--- ${t} ---`); }

// ---------- unit tests ----------
section("Unit tests");

check("fleet is the classic 5 ships / 17 cells",
  G.SHIPS.length === 5 && G.SHIPS.reduce((a, s) => a + s.len, 0) === 17);
check("board is 10x10", G.SIZE === 10);

{
  const b = G.emptyBoard();
  check("empty board has no ships", b.ships.length === 0);
  check("canPlace rejects horizontal overflow", !G.canPlace(b, 0, 6, 5, true));
  check("canPlace rejects vertical overflow", !G.canPlace(b, 6, 0, 5, false));
  check("canPlace accepts exact fit", G.canPlace(b, 0, 5, 5, true));
  G.placeShip(b, { name: "Carrier", len: 5 }, 0, 0, true);
  check("placed ship occupies len cells",
    b.ships[0].cells.length === 5 && b.shipAt[0][4] !== null && b.shipAt[0][5] === null);
  check("canPlace rejects overlap", !G.canPlace(b, 0, 3, 3, true));
  check("canPlace allows adjacency (classic rules)", G.canPlace(b, 1, 0, 3, true));
}

{
  const b = G.emptyBoard();
  G.placeShip(b, { name: "Destroyer", len: 2 }, 3, 3, true);
  check("miss recorded", G.fire(b, 0, 0).hit === false && b.shots[0][0] === "miss");
  const h1 = G.fire(b, 3, 3);
  check("hit recorded", h1.hit === true && b.shots[3][3] === "hit" && h1.ship.sunk === false);
  check("repeat shot returns null and does not mutate", G.fire(b, 3, 3) === null && h1.ship.hits === 1);
  const h2 = G.fire(b, 3, 4);
  check("ship sinks on final hit", h2.ship.sunk === true);
  check("allSunk true when every ship sunk", G.allSunk(b) === true);
}

check("coordName maps to classic labels",
  G.coordName(0, 0) === "A1" && G.coordName(9, 9) === "J10" && G.coordName(2, 4) === "C5");

{
  // AI target queue behaviour
  const b = G.emptyBoard();
  const ship = G.placeShip(b, { name: "Destroyer", len: 2 }, 5, 5, true);
  let targets = [];
  const res = G.fire(b, 5, 5);
  targets = G.aiUpdateTargets(targets, 5, 5, res);
  check("AI queues 4 neighbours after a hit", targets.length === 4);
  const res2 = G.fire(b, 5, 6);
  targets = G.aiUpdateTargets(targets, 5, 6, res2);
  check("AI clears queued cells of a sunk ship",
    ship.sunk && !targets.some(([r, c]) => r === 5 && c === 6));
  const b2 = G.emptyBoard();
  check("AI skips out-of-bounds / already-shot queued cells", (() => {
    const t = [[-1, 0], [0, 0]];
    b2.shots[0][0] = "miss";
    const pick = G.aiChooseShot(b2, t);
    return pick[0] >= 0 && pick[1] >= 0 && !b2.shots[pick[0]][pick[1]];
  })());
}

{
  // randomizeBoard legality over many trials
  let ok = true, detail = "";
  for (let i = 0; i < 500; i++) {
    const b = G.emptyBoard();
    G.randomizeBoard(b);
    let cells = 0;
    for (let r = 0; r < 10; r++) for (let c = 0; c < 10; c++) if (b.shipAt[r][c]) cells++;
    if (b.ships.length !== 5 || cells !== 17) { ok = false; detail = `trial ${i}: ${b.ships.length} ships, ${cells} cells`; break; }
    for (const s of b.ships) {
      const rs = new Set(s.cells.map(x => x[0])), cs = new Set(s.cells.map(x => x[1]));
      const straight = rs.size === 1 || cs.size === 1;
      const idx = (rs.size === 1 ? s.cells.map(x => x[1]) : s.cells.map(x => x[0])).sort((a, b) => a - b);
      const contiguous = idx.every((v, k) => k === 0 || v === idx[k - 1] + 1);
      const inBounds = s.cells.every(([r, c]) => r >= 0 && r < 10 && c >= 0 && c < 10);
      if (!straight || !contiguous || !inBounds) { ok = false; detail = `trial ${i}: bad ship ${s.name}`; break; }
    }
    if (!ok) break;
  }
  check("500 random fleets: 5 ships, 17 cells, straight, contiguous, in bounds, no overlap", ok, detail);
}

// ---------- 30 simulated games ----------
section("30 simulated full games (AI vs AI, real turn rules)");

function playGame(gameNo) {
  const errors = [];
  const boards = [G.emptyBoard(), G.emptyBoard()];
  boards.forEach(b => G.randomizeBoard(b));
  const targets = [[], []];
  let turn = 0, shots = [0, 0], hits = [0, 0], guard = 0;

  while (!G.allSunk(boards[0]) && !G.allSunk(boards[1])) {
    if (++guard > 1000) { errors.push("game did not terminate within 1000 shots"); break; }
    const opp = boards[1 - turn];
    const [r, c] = G.aiChooseShot(opp, targets[turn]);
    if (r == null || c == null) { errors.push("AI returned no shot"); break; }
    if (r < 0 || r > 9 || c < 0 || c > 9) { errors.push(`AI shot out of bounds ${r},${c}`); break; }
    if (opp.shots[r][c]) { errors.push(`AI repeated a shot at ${G.coordName(r, c)}`); break; }
    const res = G.fire(opp, r, c);
    if (res === null) { errors.push("fire() rejected a fresh cell"); break; }
    targets[turn] = G.aiUpdateTargets(targets[turn], r, c, res);
    shots[turn]++;
    if (res.hit) hits[turn]++;

    // invariants after every shot
    for (const b of boards) {
      let hitCells = 0, shipHits = 0;
      for (let rr = 0; rr < 10; rr++) for (let cc = 0; cc < 10; cc++) {
        if (b.shots[rr][cc] === "hit") {
          hitCells++;
          if (!b.shipAt[rr][cc]) errors.push("hit marked on empty water");
        }
        if (b.shots[rr][cc] === "miss" && b.shipAt[rr][cc]) errors.push("miss marked on a ship");
      }
      for (const s of b.ships) {
        shipHits += s.hits;
        if (s.hits > s.len) errors.push(`${s.name} has more hits than length`);
        if (s.sunk !== (s.hits === s.len)) errors.push(`${s.name} sunk flag inconsistent`);
        const marked = s.cells.filter(([rr, cc]) => b.shots[rr][cc] === "hit").length;
        if (marked !== s.hits) errors.push(`${s.name} hit count != marked cells`);
      }
      if (hitCells !== shipHits) errors.push("board hit total != sum of ship hits");
    }
    // classic rule under test: hit => same player fires again
    if (!res.hit) turn = 1 - turn;
  }

  const loserIdx = G.allSunk(boards[0]) ? 0 : (G.allSunk(boards[1]) ? 1 : -1);
  if (loserIdx === -1) errors.push("no side lost");
  else {
    const loser = boards[loserIdx];
    if (loser.ships.some(s => !s.sunk)) errors.push("game ended with ships afloat");
    if (loser.ships.reduce((a, s) => a + s.hits, 0) !== 17) errors.push("winner did not land exactly 17 hits");
  }
  const winner = 1 - loserIdx;
  return { gameNo, errors, shots: shots[winner], hits: hits[winner], winner };
}

const results = [];
for (let i = 1; i <= 30; i++) results.push(playGame(i));

for (const r of results) {
  const label = `Game ${String(r.gameNo).padStart(2, " ")}: winner P${r.winner + 1} in ${String(r.shots).padStart(3, " ")} shots (${r.hits} hits)`;
  console.log(r.errors.length ? `${label}  FAIL -> ${r.errors.join("; ")}` : `${label}  ok`);
  check(`game ${r.gameNo} clean`, r.errors.length === 0, r.errors.join("; "));
}
const shotCounts = results.map(r => r.shots);
console.log(`\nWinner shot counts: min ${Math.min(...shotCounts)}, max ${Math.max(...shotCounts)}, avg ${(shotCounts.reduce((a, b) => a + b, 0) / 30).toFixed(1)} (random play would average ~95)`);
check("AI shot counts are plausible (17..100)", shotCounts.every(s => s >= 17 && s <= 100));

section("Summary");
console.log(`${passed} checks passed, ${failures.length} failed`);
if (failures.length) {
  failures.forEach(f => console.log("  FAIL " + f));
  process.exit(1);
}
