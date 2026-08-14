# Battleship

Classic Battleship against the computer, in a single self-contained HTML file. No build, no dependencies — open `index.html` in a browser.

## Rules as implemented

- 10x10 grids, coordinates A1–J10.
- Standard fleet: Carrier (5), Battleship (4), Cruiser (3), Submarine (3), Destroyer (2) — 17 cells.
- Ships are placed horizontally or vertically, may touch, may not overlap.
- A hit earns another shot; a miss passes the turn.
- First side to sink all five enemy ships wins.

## Playing

Click cells on **Your Fleet** to place each ship (`R` or the Rotate button toggles orientation), or press **Random Placement**. Then click **Enemy Waters** to fire. **New Game** resets.

Placing a ship thunks as the hull settles into the water. Shots play synthesized sound effects — a splash on a miss, an explosion on a hit. **Sound: On/Off** mutes them. Nothing is downloaded; the audio is generated with the Web Audio API.

When the last ship of a fleet goes down, a victory or defeat card appears over the boards (both grids stay visible) with a **New Game** button, plus an ascending major fanfare on a win and a descending minor jingle on a loss.

The computer hunts on a checkerboard parity pattern and switches to targeting the neighbours of an unresolved hit until the ship sinks (~53 shots to win, vs ~95 for random fire).

## Tests

```bash
tests/run-all.sh
```

- `tests/run-tests.js` (Node, no deps) extracts the `CORE LOGIC` block verbatim from `index.html` and runs unit tests plus **30 full simulated games** with per-shot invariant checks (hit/miss accounting, sink detection, no repeat shots, termination in exactly 17 hits). Deterministic PRNG, so failures reproduce.
- `tests/ui-test.py` drives the real page in Chrome over CDP and asserts on the rendered DOM: placement legality and previews, turn rules, the turn lock during the computer's delay, end-of-game state, and reset. Requires Chrome with remote debugging (`CDP_URL`, default `http://localhost:29229`) and `pip install websocket-client`.
