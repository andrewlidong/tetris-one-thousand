/**
 * Tetris × 1000 — Client
 * Canvas-based multiplayer Tetris frontend.
 */

// ── Color palette ─────────────────────────────────────────────────────────────
const COLORS = [
  null,
  "#00f0f0",  // 1 I  cyan
  "#f0f000",  // 2 O  yellow
  "#a000f0",  // 3 T  purple
  "#00d000",  // 4 S  green
  "#f00000",  // 5 Z  red
  "#0050f0",  // 6 J  blue
  "#f09000",  // 7 L  orange
  "#707070",  // 8 garbage gray
];

const GHOST_ALPHA = "44"; // hex suffix for ghost transparency

// Preview shapes for hold / next panels (rotation 0)
const PIECE_SHAPES = [
  [[0,0,0,0],[1,1,1,1]],           // I
  [[0,1,1,0],[0,1,1,0]],           // O
  [[0,1,0],[1,1,1]],               // T
  [[0,1,1],[1,1,0]],               // S
  [[1,1,0],[0,1,1]],               // Z
  [[1,0,0],[1,1,1]],               // J
  [[0,0,1],[1,1,1]],               // L
];

// ── Layout constants (canvas 1400 × 900) ──────────────────────────────────────
const CW = 1400, CH = 900;
const CS = 24;       // cell size px (main board)
const BW = 10, BH = 20;

// Panels
const HOLD_X = 8,  HOLD_Y = 50;
const BOARD_X = 128, BOARD_Y = 50;
const NEXT_X = BOARD_X + BW * CS + 18, NEXT_Y = 50;
const INFO_X = 8, INFO_Y = 160;
const LB_X = CW - 250, LB_Y = 10;

// Mini-board grid (top-left of the overview area)
const MINI_CELL = 5;
const MINI_W = BW * MINI_CELL;   // 50px
const MINI_H = BH * MINI_CELL;   // 100px
const MINI_LABEL_H = 14;
const MINI_PAD = 6;
const MINI_ITEM_W = MINI_W + MINI_PAD;
const MINI_ITEM_H = MINI_H + MINI_LABEL_H + MINI_PAD;
const MINI_AREA_X = NEXT_X + 110;
const MINI_AREA_Y = BOARD_Y;
const MINI_COLS = Math.floor((LB_X - MINI_AREA_X - 10) / MINI_ITEM_W);

// ── TetrisClient ──────────────────────────────────────────────────────────────
class TetrisClient {
  constructor(playerName) {
    this.playerName = playerName;
    this.playerId = null;
    this.state = null;    // own board state
    this.overview = null; // latest broadcast

    this.canvas = document.getElementById("gameCanvas");
    this.ctx = this.canvas.getContext("2d");
    this.canvas.width = CW;
    this.canvas.height = CH;

    this.ws = null;
    this.connected = false;

    // DAS (Delayed Auto Shift)
    this.keys = {};           // code → timestamp pressed
    this.dasTimer = {};       // code → next repeat timestamp
    this.DAS_DELAY = 170;
    this.DAS_RATE  = 50;

    this._scaleCanvas();
    window.addEventListener("resize", () => this._scaleCanvas());

    document.addEventListener("keydown", (e) => this._onKeyDown(e));
    document.addEventListener("keyup",   (e) => { delete this.keys[e.code]; });

    this._connect();
    this._loop();
  }

  // ── Canvas scaling ─────────────────────────────────────────────────────────
  _scaleCanvas() {
    const scale = Math.min(
      window.innerWidth  / CW,
      window.innerHeight / CH,
    );
    this.canvas.style.transform       = `scale(${scale})`;
    this.canvas.style.transformOrigin = "top left";
    this.canvas.style.position        = "absolute";
    this.canvas.style.left = `${(window.innerWidth  - CW * scale) / 2}px`;
    this.canvas.style.top  = `${(window.innerHeight - CH * scale) / 2}px`;
  }

  // ── WebSocket ──────────────────────────────────────────────────────────────
  _connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(`${proto}//${location.host}/ws`);

    this.ws.onopen = () => {
      this.connected = true;
      if (this.playerName) {
        this._send({ type: "name", name: this.playerName });
      }
    };

    this.ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if      (data.type === "init")     this.playerId = data.player_id;
      else if (data.type === "state")    this.state    = data;
      else if (data.type === "overview") this.overview = data;
    };

    this.ws.onclose = () => {
      this.connected = false;
      setTimeout(() => this._connect(), 2000);
    };
    this.ws.onerror = () => this.ws.close();
  }

  _send(obj) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  _input(action) { this._send({ type: "input", action }); }

  // ── Keyboard ───────────────────────────────────────────────────────────────
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
    if (this.keys[e.code]) return; // already held
    this.keys[e.code] = Date.now();

    const action = this._ACTION_MAP[e.code];
    if (action) {
      e.preventDefault();
      this._input(action);
      this.dasTimer[e.code] = Date.now() + this.DAS_DELAY;
    }

    if (e.code === "KeyR" && this.state && !this.state.alive) {
      this._send({ type: "restart" });
    }
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

  // ── Render loop ───────────────────────────────────────────────────────────
  _loop() {
    this._handleDAS();
    this._draw();
    requestAnimationFrame(() => this._loop());
  }

  _draw() {
    const ctx = this.ctx;
    ctx.fillStyle = "#0d0d1a";
    ctx.fillRect(0, 0, CW, CH);

    if (!this.connected) {
      this._text(ctx, "Connecting…", CW / 2, CH / 2, "#fff", "24px", "center");
      return;
    }

    this._drawBoard(ctx);
    this._drawHold(ctx);
    this._drawNext(ctx);
    this._drawInfo(ctx);
    if (this.overview) {
      this._drawOverview(ctx);
    }
  }

  // ── Main board ────────────────────────────────────────────────────────────
  _drawBoard(ctx) {
    const bx = BOARD_X, by = BOARD_Y;

    // Background + grid
    ctx.fillStyle = "#080812";
    ctx.fillRect(bx, by, BW * CS, BH * CS);
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= BW; x++) {
      ctx.beginPath(); ctx.moveTo(bx + x * CS, by);
      ctx.lineTo(bx + x * CS, by + BH * CS); ctx.stroke();
    }
    for (let y = 0; y <= BH; y++) {
      ctx.beginPath(); ctx.moveTo(bx, by + y * CS);
      ctx.lineTo(bx + BW * CS, by + y * CS); ctx.stroke();
    }

    // Cells
    if (this.state) {
      const board = this.state.board;
      for (let r = 0; r < BH; r++) {
        for (let c = 0; c < BW; c++) {
          const v = board[r][c];
          if (!v) continue;
          const ghost = v < 0;
          const idx = Math.abs(v);
          this._drawCell(ctx, bx + c * CS, by + r * CS, CS, COLORS[idx], ghost);
        }
      }
    }

    // Border
    ctx.strokeStyle = "#3a3a8a";
    ctx.lineWidth = 2;
    ctx.strokeRect(bx, by, BW * CS, BH * CS);

    // Garbage indicator bar (left of board)
    if (this.state && this.state.garbage_in > 0) {
      const barH = Math.min(BH * CS, this.state.garbage_in * CS);
      ctx.fillStyle = "#ff3333";
      ctx.fillRect(bx - 10, by + BH * CS - barH, 7, barH);
    }

    // Game-over overlay
    if (this.state && !this.state.alive) {
      ctx.fillStyle = "rgba(0,0,0,0.75)";
      ctx.fillRect(bx, by, BW * CS, BH * CS);
      this._text(ctx, "GAME OVER", bx + BW * CS / 2, by + BH * CS / 2 - 18, "#ff4444", "bold 30px", "center");
      this._text(ctx, "Press R to restart", bx + BW * CS / 2, by + BH * CS / 2 + 18, "#aaa", "16px", "center");
    }
  }

  _drawCell(ctx, x, y, size, color, ghost = false) {
    if (ghost) {
      ctx.fillStyle = color + GHOST_ALPHA;
      ctx.fillRect(x + 1, y + 1, size - 2, size - 2);
      return;
    }
    ctx.fillStyle = color;
    ctx.fillRect(x + 1, y + 1, size - 2, size - 2);
    // Highlight top/left
    ctx.fillStyle = "rgba(255,255,255,0.25)";
    ctx.fillRect(x + 1, y + 1, size - 2, 3);
    ctx.fillRect(x + 1, y + 1, 3, size - 2);
    // Shadow bottom/right
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fillRect(x + 1, y + size - 4, size - 2, 3);
    ctx.fillRect(x + size - 4, y + 1, 3, size - 2);
  }

  // ── Piece preview (hold / next) ──────────────────────────────────────────
  _drawPiecePreview(ctx, pieceType, cx, cy, cellSize) {
    if (pieceType == null) return;
    const shape = PIECE_SHAPES[pieceType];
    const color = COLORS[pieceType + 1];
    const cols = shape[0].length, rows = shape.length;
    const ox = cx - (cols * cellSize) / 2;
    const oy = cy - (rows * cellSize) / 2;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (shape[r][c]) {
          this._drawCell(ctx, ox + c * cellSize, oy + r * cellSize, cellSize, color);
        }
      }
    }
  }

  _drawHold(ctx) {
    const hx = HOLD_X, hy = HOLD_Y;
    this._label(ctx, "HOLD", hx, hy - 6);
    ctx.fillStyle = "#080812";
    ctx.fillRect(hx, hy, 110, 80);
    ctx.strokeStyle = "#3a3a8a"; ctx.lineWidth = 1;
    ctx.strokeRect(hx, hy, 110, 80);
    if (this.state) {
      this._drawPiecePreview(ctx, this.state.held, hx + 55, hy + 40, 18);
    }
  }

  _drawNext(ctx) {
    const nx = NEXT_X, ny = NEXT_Y;
    this._label(ctx, "NEXT", nx, ny - 6);
    if (!this.state) return;
    const nexts = this.state.next ?? [];
    for (let i = 0; i < Math.min(5, nexts.length); i++) {
      ctx.fillStyle = "#080812";
      ctx.fillRect(nx, ny + i * 62, 90, 58);
      ctx.strokeStyle = "#3a3a8a"; ctx.lineWidth = 1;
      ctx.strokeRect(nx, ny + i * 62, 90, 58);
      this._drawPiecePreview(ctx, nexts[i], nx + 45, ny + i * 62 + 29, 14);
    }
  }

  // ── Score info panel ──────────────────────────────────────────────────────
  _drawInfo(ctx) {
    if (!this.state) return;
    const ix = INFO_X;
    let iy = INFO_Y;

    const rows = [
      ["SCORE", this.state.score.toLocaleString()],
      ["LEVEL", this.state.level],
      ["LINES", this.state.lines],
    ];
    for (const [label, val] of rows) {
      this._label(ctx, label, ix, iy);
      this._text(ctx, String(val), ix, iy + 22, "#ffffff", "bold 20px");
      iy += 52;
    }

    // Controls reference
    iy += 10;
    const ctrls = [
      "← → move",
      "↑ / X  rotate CW",
      "Z       rotate CCW",
      "↓       soft drop",
      "SPC   hard drop",
      "C/⇧   hold",
      "R       restart",
    ];
    for (const c of ctrls) {
      this._text(ctx, c, ix, iy, "#555", "11px");
      iy += 15;
    }
  }

  // ── Overview (mini boards + leaderboard) ──────────────────────────────────
  _drawOverview(ctx) {
    const ov = this.overview;

    // Status bar
    ctx.fillStyle = "#111124";
    ctx.fillRect(0, CH - 22, MINI_AREA_X - 5, 22);
    this._text(
      ctx,
      `Players: ${ov.total}   Alive: ${ov.alive}`,
      10, CH - 7, "#00f0f0", "bold 13px"
    );

    // Mini boards grid
    const boards = ov.boards ?? {};
    let idx = 0;
    for (const [pidStr, bd] of Object.entries(boards)) {
      const col = idx % MINI_COLS;
      const row = Math.floor(idx / MINI_COLS);
      const bx = MINI_AREA_X + col * MINI_ITEM_W;
      const by = MINI_AREA_Y + row * MINI_ITEM_H;
      if (by + MINI_ITEM_H > CH - 5) break;

      const isMe = parseInt(pidStr) === this.playerId;

      // Highlight own board
      if (isMe) {
        ctx.fillStyle = "rgba(0,240,240,0.15)";
        ctx.fillRect(bx - 2, by, MINI_ITEM_W, MINI_ITEM_H);
      }

      // Background
      ctx.fillStyle = "#060610";
      ctx.fillRect(bx, by + MINI_LABEL_H, MINI_W, MINI_H);

      // Decode compact board string
      const encoded = bd.b;
      for (let r = 0; r < BH; r++) {
        for (let c = 0; c < BW; c++) {
          const v = parseInt(encoded[r * BW + c]);
          if (v > 0) {
            ctx.fillStyle = COLORS[v] ?? "#888";
            ctx.fillRect(
              bx + c * MINI_CELL,
              by + MINI_LABEL_H + r * MINI_CELL,
              MINI_CELL - 1, MINI_CELL - 1
            );
          }
        }
      }

      // Name
      ctx.fillStyle = isMe ? "#00f0f0" : "#777";
      ctx.font = "8px monospace";
      ctx.textAlign = "left";
      const shortName = bd.name.length > 9 ? bd.name.slice(0, 8) + "…" : bd.name;
      ctx.fillText(shortName, bx, by + MINI_LABEL_H - 3);

      idx++;
    }

    // Leaderboard
    this._drawLeaderboard(ctx, ov.leaderboard ?? []);
  }

  _drawLeaderboard(ctx, lb) {
    const lx = LB_X, ly = LB_Y;
    const rowH = 20, padX = 10, headH = 28;
    const boxH = headH + Math.min(25, lb.length) * rowH + 8;

    ctx.fillStyle = "rgba(8,8,20,0.92)";
    ctx.fillRect(lx, ly, 240, boxH);
    ctx.strokeStyle = "#3a3a8a"; ctx.lineWidth = 1;
    ctx.strokeRect(lx, ly, 240, boxH);

    this._text(ctx, "LEADERBOARD", lx + padX, ly + 18, "#00f0f0", "bold 13px");

    for (let i = 0; i < Math.min(25, lb.length); i++) {
      const e = lb[i];
      const ey = ly + headH + i * rowH;
      const isMe = e.id === this.playerId;
      const color = isMe ? "#00f0f0" : (e.alive ? "#ccc" : "#444");
      const font = isMe ? "bold 11px monospace" : "11px monospace";

      ctx.fillStyle = color;
      ctx.font = font;
      ctx.textAlign = "left";
      const rank = String(i + 1).padStart(2, " ");
      const name = e.name.length > 11 ? e.name.slice(0, 10) + "…" : e.name.padEnd(11);
      ctx.fillText(`${rank}. ${name}`, lx + padX, ey + 14);
      ctx.textAlign = "right";
      ctx.fillText(e.score.toLocaleString(), lx + 230, ey + 14);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  _text(ctx, text, x, y, color, font, align = "left") {
    ctx.fillStyle = color;
    ctx.font = `${font} monospace`;
    ctx.textAlign = align;
    ctx.fillText(text, x, y);
  }

  _label(ctx, text, x, y) {
    ctx.fillStyle = "#555";
    ctx.font = "bold 11px monospace";
    ctx.textAlign = "left";
    ctx.fillText(text, x, y);
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  const modal   = document.getElementById("nameModal");
  const input   = document.getElementById("nameInput");
  const btn     = document.getElementById("startBtn");
  const canvas  = document.getElementById("gameCanvas");

  const saved = localStorage.getItem("tetris_name");
  if (saved) input.value = saved;

  function start() {
    const name = input.value.trim() || `Guest${Math.floor(Math.random() * 9999)}`;
    localStorage.setItem("tetris_name", name);
    modal.style.display = "none";
    canvas.style.display = "block";
    new TetrisClient(name);
  }

  btn.addEventListener("click", start);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") start(); });
});
