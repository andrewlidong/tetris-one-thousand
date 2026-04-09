/**
 * Tetris × 1000 — Cooperative Massive Board Client
 * All players share one 100×30 board.
 */

// ── Constants (must match server) ─────────────────────────────────────────────
const BW = 100, BH = 30;   // board dimensions
const CS = 10;              // cell size in px

// Canvas dimensions
const CW = 1400, CH = 700;

// Layout geometry
const BOARD_X = 120, BOARD_Y = 60;                       // board top-left on canvas
const LEFT_X  = 4,   LEFT_Y  = 50;                       // left info panel
const RIGHT_X = BOARD_X + BW * CS + 10;                  // = 1110

// ── Piece rotation tables (mirror server exactly) ──────────────────────────────
const PIECES = [
  // 0 I
  [
    [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
    [[0,0,1,0],[0,0,1,0],[0,0,1,0],[0,0,1,0]],
    [[0,0,0,0],[0,0,0,0],[1,1,1,1],[0,0,0,0]],
    [[0,1,0,0],[0,1,0,0],[0,1,0,0],[0,1,0,0]],
  ],
  // 1 O
  [
    [[0,1,1,0],[0,1,1,0],[0,0,0,0]],
    [[0,1,1,0],[0,1,1,0],[0,0,0,0]],
    [[0,1,1,0],[0,1,1,0],[0,0,0,0]],
    [[0,1,1,0],[0,1,1,0],[0,0,0,0]],
  ],
  // 2 T
  [
    [[0,1,0],[1,1,1],[0,0,0]],
    [[0,1,0],[0,1,1],[0,1,0]],
    [[0,0,0],[1,1,1],[0,1,0]],
    [[0,1,0],[1,1,0],[0,1,0]],
  ],
  // 3 S
  [
    [[0,1,1],[1,1,0],[0,0,0]],
    [[0,1,0],[0,1,1],[0,0,1]],
    [[0,0,0],[0,1,1],[1,1,0]],
    [[1,0,0],[1,1,0],[0,1,0]],
  ],
  // 4 Z
  [
    [[1,1,0],[0,1,1],[0,0,0]],
    [[0,0,1],[0,1,1],[0,1,0]],
    [[0,0,0],[1,1,0],[0,1,1]],
    [[0,1,0],[1,1,0],[1,0,0]],
  ],
  // 5 J
  [
    [[1,0,0],[1,1,1],[0,0,0]],
    [[0,1,1],[0,1,0],[0,1,0]],
    [[0,0,0],[1,1,1],[0,0,1]],
    [[0,1,0],[0,1,0],[1,1,0]],
  ],
  // 6 L
  [
    [[0,0,1],[1,1,1],[0,0,0]],
    [[0,1,0],[0,1,0],[0,1,1]],
    [[0,0,0],[1,1,1],[1,0,0]],
    [[1,1,0],[0,1,0],[0,1,0]],
  ],
];

// Preview shapes (rotation 0, trimmed) for hold/next panels
const PIECE_SHAPES = [
  [[0,0,0,0],[1,1,1,1]],
  [[0,1,1,0],[0,1,1,0]],
  [[0,1,0],[1,1,1]],
  [[0,1,1],[1,1,0]],
  [[1,1,0],[0,1,1]],
  [[1,0,0],[1,1,1]],
  [[0,0,1],[1,1,1]],
];

const COLORS = [
  null,
  "#00f0f0",  // 1 I  cyan
  "#f0f000",  // 2 O  yellow
  "#a000f0",  // 3 T  purple
  "#00d000",  // 4 S  green
  "#f00000",  // 5 Z  red
  "#0050f0",  // 6 J  blue
  "#f09000",  // 7 L  orange
  "#707070",  // 8 garbage
];

// ── TetrisClient ───────────────────────────────────────────────────────────────
class TetrisClient {
  constructor(playerName) {
    this.playerName = playerName;
    this.playerId   = null;
    this.state      = null;   // own piece state from server
    this.worldData  = null;   // latest world broadcast

    // Decoded settled board (BH × BW Uint8Array rows)
    this.board = Array.from({ length: BH }, () => new Uint8Array(BW));

    this.canvas = document.getElementById("gameCanvas");
    this.ctx    = this.canvas.getContext("2d");
    this.canvas.width  = CW;
    this.canvas.height = CH;

    this.ws        = null;
    this.connected = false;

    // Keyboard / DAS
    this.keys     = {};
    this.dasTimer = {};
    this.DAS_DELAY = 150;
    this.DAS_RATE  = 50;

    this._scaleCanvas();
    window.addEventListener("resize", () => this._scaleCanvas());
    document.addEventListener("keydown", (e) => this._onKeyDown(e));
    document.addEventListener("keyup",   (e) => { delete this.keys[e.code]; });

    this._connect();
    requestAnimationFrame(() => this._loop());
  }

  // ── Canvas scaling ──────────────────────────────────────────────────────────
  _scaleCanvas() {
    const scale = Math.min(window.innerWidth / CW, window.innerHeight / CH);
    Object.assign(this.canvas.style, {
      transform:       `scale(${scale})`,
      transformOrigin: "top left",
      position:        "absolute",
      left: `${(window.innerWidth  - CW * scale) / 2}px`,
      top:  `${(window.innerHeight - CH * scale) / 2}px`,
    });
  }

  // ── WebSocket ───────────────────────────────────────────────────────────────
  _connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(`${proto}//${location.host}/ws`);

    this.ws.onopen = () => {
      this.connected = true;
      if (this.playerName) this._send({ type: "name", name: this.playerName });
    };

    this.ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if      (data.type === "init")  this.playerId = data.player_id;
      else if (data.type === "state") this.state    = data;
      else if (data.type === "board") this._decodeBoard(data.b);
      else if (data.type === "world") {
        this.worldData = data;
        if (data.board) this._decodeBoard(data.board);
      }
    };

    this.ws.onclose = () => { this.connected = false; setTimeout(() => this._connect(), 2000); };
    this.ws.onerror = ()  => this.ws.close();
  }

  _send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN)
      this.ws.send(JSON.stringify(obj));
  }

  _input(action) { this._send({ type: "input", action }); }

  // ── Board decoding ──────────────────────────────────────────────────────────
  _decodeBoard(encoded) {
    if (!encoded || encoded.length !== BW * BH) return;
    for (let r = 0; r < BH; r++)
      for (let c = 0; c < BW; c++)
        this.board[r][c] = parseInt(encoded[r * BW + c], 16);
  }

  // ── Keyboard / DAS ─────────────────────────────────────────────────────────
  _ACTION_MAP = {
    ArrowLeft:  "left",
    ArrowRight: "right",
    ArrowDown:  "down",
    Space:      "hard_drop",
    ArrowUp:    "rotate_cw",
    KeyX:       "rotate_cw",
    KeyZ:       "rotate_ccw",
    KeyC:       "hold",
    ShiftLeft:  "hold",
    ShiftRight: "hold",
  };

  _onKeyDown(e) {
    if (this.keys[e.code]) return;
    this.keys[e.code] = true;

    const action = this._ACTION_MAP[e.code];
    if (action) {
      e.preventDefault();
      this._input(action);
      this.dasTimer[e.code] = Date.now() + this.DAS_DELAY;
    }

    if (e.code === "KeyR" && this.state && !this.state.alive)
      this._send({ type: "restart" });
  }

  _handleDAS() {
    const now = Date.now();
    for (const code of ["ArrowLeft", "ArrowRight", "ArrowDown"]) {
      if (this.keys[code] && now >= (this.dasTimer[code] ?? Infinity)) {
        this._input(this._ACTION_MAP[code]);
        this.dasTimer[code] = now + this.DAS_RATE;
      }
    }
  }

  // ── Render loop ─────────────────────────────────────────────────────────────
  _loop() {
    this._handleDAS();
    this._draw();
    requestAnimationFrame(() => this._loop());
  }

  _draw() {
    const ctx = this.ctx;
    ctx.fillStyle = "#080812";
    ctx.fillRect(0, 0, CW, CH);

    if (!this.connected) {
      ctx.fillStyle = "#aaa";
      ctx.font = "22px monospace";
      ctx.textAlign = "center";
      ctx.fillText("Connecting…", CW / 2, CH / 2);
      return;
    }

    this._drawHeader(ctx);
    this._drawBoard(ctx);
    this._drawLeftPanel(ctx);
    this._drawRightPanel(ctx);
  }

  // ── Header ─────────────────────────────────────────────────────────────────
  _drawHeader(ctx) {
    ctx.fillStyle = "#00f0f0";
    ctx.font = "bold 17px monospace";
    ctx.textAlign = "center";
    ctx.fillText("TETRIS × 1000  —  COOPERATIVE", BOARD_X + BW * CS / 2, 22);

    const wd = this.worldData;
    if (wd) {
      ctx.fillStyle = "#666";
      ctx.font = "12px monospace";
      ctx.fillText(
        `Players: ${wd.total}   Alive: ${wd.alive}   Lines Cleared: ${wd.total_lines}`,
        BOARD_X + BW * CS / 2, 40,
      );
    }
  }

  // ── Main shared board ───────────────────────────────────────────────────────
  _drawBoard(ctx) {
    const bx = BOARD_X, by = BOARD_Y;
    const bpx = BW * CS, bpy = BH * CS;   // 1000 × 300

    // Background
    ctx.fillStyle = "#04040e";
    ctx.fillRect(bx, by, bpx, bpy);

    // Fine grid (every cell)
    ctx.strokeStyle = "rgba(255,255,255,0.025)";
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= BW; x++) {
      ctx.beginPath();
      ctx.moveTo(bx + x * CS, by);
      ctx.lineTo(bx + x * CS, by + bpy);
      ctx.stroke();
    }
    for (let y = 0; y <= BH; y++) {
      ctx.beginPath();
      ctx.moveTo(bx, by + y * CS);
      ctx.lineTo(bx + bpx, by + y * CS);
      ctx.stroke();
    }

    // Column dividers every 10 cells (standard-board-width guides)
    ctx.strokeStyle = "rgba(255,255,255,0.1)";
    ctx.lineWidth = 1;
    for (let x = 10; x < BW; x += 10) {
      ctx.beginPath();
      ctx.moveTo(bx + x * CS, by);
      ctx.lineTo(bx + x * CS, by + bpy);
      ctx.stroke();
    }

    // Settled board cells
    for (let r = 0; r < BH; r++) {
      for (let c = 0; c < BW; c++) {
        const v = this.board[r][c];
        if (v) this._cell(ctx, bx + c * CS, by + r * CS, CS, COLORS[v]);
      }
    }

    // Other players' active pieces
    if (this.worldData?.pieces) {
      for (const [pid, px, py, ptype, prot, colorIdx] of this.worldData.pieces) {
        if (pid !== this.playerId)
          this._drawPieceCells(ctx, ptype, prot, px, py, COLORS[colorIdx], "other");
      }
    }

    // Own ghost
    if (this.state?.alive && this.state.piece) {
      const p = this.state.piece;
      this._drawPieceCells(ctx, p.type, p.rot, p.x, p.ghost_y,
                           COLORS[this.state.color], "ghost");
    }

    // Own active piece (rendered last = on top)
    if (this.state?.alive && this.state.piece) {
      const p = this.state.piece;
      this._drawPieceCells(ctx, p.type, p.rot, p.x, p.y,
                           COLORS[this.state.color], "own");
    }

    // Board border
    ctx.strokeStyle = "#3a3a8a";
    ctx.lineWidth = 2;
    ctx.strokeRect(bx, by, bpx, bpy);

    // Dead overlay
    if (this.state && !this.state.alive) {
      const mx = bx + bpx / 2;
      const my = by + bpy / 2;
      ctx.fillStyle = "rgba(0,0,0,0.65)";
      ctx.fillRect(mx - 160, my - 38, 320, 76);
      ctx.strokeStyle = "#ff4444";
      ctx.lineWidth = 2;
      ctx.strokeRect(mx - 160, my - 38, 320, 76);
      ctx.fillStyle = "#ff4444";
      ctx.font = "bold 26px monospace";
      ctx.textAlign = "center";
      ctx.fillText("YOU DIED", mx, my - 6);
      ctx.fillStyle = "#999";
      ctx.font = "14px monospace";
      ctx.fillText("Press R to respawn", mx, my + 22);
    }
  }

  // ── Cell renderers ──────────────────────────────────────────────────────────
  _cell(ctx, x, y, s, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x + 1, y + 1, s - 2, s - 2);
    ctx.fillStyle = "rgba(255,255,255,0.22)";
    ctx.fillRect(x + 1, y + 1, s - 2, 2);
    ctx.fillRect(x + 1, y + 1, 2, s - 2);
    ctx.fillStyle = "rgba(0,0,0,0.28)";
    ctx.fillRect(x + 1, y + s - 3, s - 2, 2);
    ctx.fillRect(x + s - 3, y + 1, 2, s - 2);
  }

  _pieceCells(ptype, prot, px, py) {
    const shape = PIECES[ptype][prot];
    const out = [];
    for (let r = 0; r < shape.length; r++)
      for (let c = 0; c < shape[r].length; c++)
        if (shape[r][c]) out.push([px + c, py + r]);
    return out;
  }

  _drawPieceCells(ctx, ptype, prot, px, py, color, mode) {
    const bx = BOARD_X, by = BOARD_Y;
    for (const [cx, cy] of this._pieceCells(ptype, prot, px, py)) {
      if (cx < 0 || cx >= BW || cy < 0 || cy >= BH) continue;
      const sx = bx + cx * CS, sy = by + cy * CS;

      if (mode === "ghost") {
        ctx.fillStyle = color + "38";
        ctx.fillRect(sx + 1, sy + 1, CS - 2, CS - 2);
        ctx.strokeStyle = color + "80";
        ctx.lineWidth = 1;
        ctx.strokeRect(sx + 1, sy + 1, CS - 2, CS - 2);
      } else if (mode === "other") {
        // Other players' pieces: slightly transparent, no bevel
        ctx.fillStyle = color + "b0";
        ctx.fillRect(sx + 1, sy + 1, CS - 2, CS - 2);
      } else {
        // Own piece: full color + white border glow
        this._cell(ctx, sx, sy, CS, color);
        ctx.strokeStyle = "rgba(255,255,255,0.85)";
        ctx.lineWidth = 1.5;
        ctx.strokeRect(sx + 1.5, sy + 1.5, CS - 3, CS - 3);
      }
    }
  }

  // ── Left panel: hold, next, score, controls ────────────────────────────────
  _drawLeftPanel(ctx) {
    let y = LEFT_Y;
    const x = LEFT_X;

    // HOLD
    this._label(ctx, "HOLD", x, y); y += 5;
    ctx.fillStyle = "#04040e";
    ctx.fillRect(x, y, 112, 72);
    ctx.strokeStyle = "#3a3a8a"; ctx.lineWidth = 1;
    ctx.strokeRect(x, y, 112, 72);
    if (this.state?.held != null)
      this._miniPiece(ctx, this.state.held, x + 56, y + 36, 13);
    y += 82;

    // NEXT
    this._label(ctx, "NEXT", x, y); y += 5;
    const nexts = this.state?.next ?? [];
    for (let i = 0; i < Math.min(4, nexts.length); i++) {
      ctx.fillStyle = "#04040e";
      ctx.fillRect(x, y, 112, 52);
      ctx.strokeStyle = "#3a3a8a"; ctx.lineWidth = 1;
      ctx.strokeRect(x, y, 112, 52);
      this._miniPiece(ctx, nexts[i], x + 56, y + 26, 12);
      y += 57;
    }
    y += 8;

    // SCORE
    this._label(ctx, "SCORE", x, y); y += 4;
    ctx.fillStyle = "#fff";
    ctx.font = "bold 19px monospace";
    ctx.textAlign = "left";
    ctx.fillText((this.state?.score ?? 0).toLocaleString(), x, y + 18);
    y += 36;

    // Controls
    y += 6;
    const ctrls = [
      "← →   move",
      "↑ / X  rotate CW",
      "Z       rotate CCW",
      "↓       soft drop",
      "SPC   hard drop",
      "C / ⇧  hold",
      "R       respawn",
    ];
    for (const line of ctrls) {
      ctx.fillStyle = "#424";
      ctx.font = "10px monospace";
      ctx.textAlign = "left";
      ctx.fillText(line, x, y);
      y += 14;
    }
  }

  _label(ctx, text, x, y) {
    ctx.fillStyle = "#555";
    ctx.font = "bold 10px monospace";
    ctx.textAlign = "left";
    ctx.fillText(text, x, y);
  }

  _miniPiece(ctx, ptype, cx, cy, cs) {
    if (ptype === null || ptype === undefined) return;
    const shape = PIECE_SHAPES[ptype];
    const color = COLORS[ptype + 1];
    const cols = shape[0].length, rows = shape.length;
    const ox = cx - (cols * cs) / 2;
    const oy = cy - (rows * cs) / 2;
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++)
        if (shape[r][c]) this._cell(ctx, ox + c * cs, oy + r * cs, cs, color);
  }

  // ── Right panel: leaderboard ────────────────────────────────────────────────
  _drawRightPanel(ctx) {
    const wd = this.worldData;
    if (!wd) return;

    const lx = RIGHT_X, ly = 10;
    const lb = wd.leaderboard ?? [];
    const rowH = 18, padX = 8, headH = 24;
    const rows = Math.min(lb.length, 36);
    const boxH = headH + rows * rowH + 6;

    ctx.fillStyle = "rgba(4,4,14,0.95)";
    ctx.fillRect(lx, ly, 278, boxH);
    ctx.strokeStyle = "#3a3a8a"; ctx.lineWidth = 1;
    ctx.strokeRect(lx, ly, 278, boxH);

    ctx.fillStyle = "#00f0f0";
    ctx.font = "bold 12px monospace";
    ctx.textAlign = "left";
    ctx.fillText("LEADERBOARD", lx + padX, ly + 16);

    for (let i = 0; i < rows; i++) {
      const e  = lb[i];
      const ey = ly + headH + i * rowH;
      const me = e.id === this.playerId;
      ctx.fillStyle = me ? "#00f0f0" : (e.alive ? "#ccc" : "#444");
      ctx.font = (me ? "bold " : "") + "10px monospace";
      ctx.textAlign = "left";
      const rank = String(i + 1).padStart(2);
      const name = e.name.length > 13 ? e.name.slice(0, 12) + "…" : e.name;
      ctx.fillText(`${rank}. ${name}`, lx + padX, ey + 13);
      ctx.textAlign = "right";
      ctx.fillText(e.score.toLocaleString(), lx + 270, ey + 13);
    }
  }
}

// ── Entry point ────────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  const modal  = document.getElementById("nameModal");
  const input  = document.getElementById("nameInput");
  const btn    = document.getElementById("startBtn");
  const canvas = document.getElementById("gameCanvas");

  const saved = localStorage.getItem("tetris_name");
  if (saved) input.value = saved;

  function start() {
    const name = input.value.trim() || `Guest${Math.floor(Math.random() * 9999)}`;
    localStorage.setItem("tetris_name", name);
    modal.style.display  = "none";
    canvas.style.display = "block";
    new TetrisClient(name);
  }

  btn.addEventListener("click", start);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
});
