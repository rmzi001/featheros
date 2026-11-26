#!/usr/bin/env python3
"""FeatherOS Live Browser VNC Console (zero external dependencies).

Serves an interactive HTML5 Canvas RFB 3.8 WebSocket client on http://127.0.0.1:8765
that connects directly to QEMU's built-in WebSocket VNC (-vnc 127.0.0.1:0,websocket=5701).
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>FeatherOS v0.3.0 — Live Interactive VM Console</title>
<style>
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; height: 100%; overflow: hidden;
    background: #070b14; color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    display: flex; flex-direction: column;
  }
  header {
    height: 44px; padding: 0 14px;
    background: #0f172a; border-bottom: 1px solid #1e293b;
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    flex-shrink: 0;
  }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 14px; color: #38bdf8; }
  .pill {
    font-size: 12px; font-weight: 500; padding: 3px 9px; border-radius: 999px;
    background: #1e293b; color: #94a3b8; border: 1px solid #334155;
  }
  .pill.ok { color: #34d399; border-color: #065f46; background: #064e3b44; }
  .pill.err { color: #f87171; border-color: #7f1d1d; background: #7f1d1d44; }
  .controls { display: flex; align-items: center; gap: 8px; }
  button {
    background: #1e293b; color: #e2e8f0; border: 1px solid #334155;
    border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer;
  }
  button:hover { background: #334155; border-color: #38bdf8; color: #fff; }
  main {
    flex: 1; display: flex; align-items: center; justify-content: center;
    padding: 8px; overflow: hidden; position: relative;
  }
  canvas {
    background: #000; border: 1px solid #1e293b; border-radius: 4px;
    max-width: 100%; max-height: 100%; object-fit: contain;
    box-shadow: 0 12px 40px rgba(0,0,0,0.65); outline: none;
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span>FeatherOS v0.3.0 — Live QEMU Console</span>
    <span id="status" class="pill">Connecting to VM...</span>
  </div>
  <div class="controls">
    <button id="btnSuper" title="Send Windows / Start key">❖ Start Key</button>
    <button id="btnCad" title="Send Ctrl+Alt+Del">Ctrl+Alt+Del</button>
    <button id="btnReconnect">Reconnect</button>
    <button id="btnFull">Fullscreen</button>
  </div>
</header>
<main>
  <canvas id="screen" width="800" height="600" tabindex="0"></canvas>
</main>
<script>
(() => {
  const WS_URL = "ws://127.0.0.1:__WS_PORT__";
  const canvas = document.getElementById("screen");
  const ctx = canvas.getContext("2d", { alpha: false });
  const statusEl = document.getElementById("status");

  let ws = null;
  let fbW = 800, fbH = 600;
  let btnMask = 0;
  let reconnectTimer = null;

  function setStatus(text, kind = "") {
    statusEl.textContent = text;
    statusEl.className = "pill" + (kind ? " " + kind : "");
  }

  class ByteQueue {
    constructor() { this.chunks = []; this.len = 0; }
    push(ab) {
      const u8 = new Uint8Array(ab);
      if (u8.length) { this.chunks.push(u8); this.len += u8.length; }
    }
    peek(n) {
      if (this.len < n) return null;
      const out = new Uint8Array(n);
      let off = 0;
      for (const c of this.chunks) {
        const take = Math.min(c.length, n - off);
        out.set(c.subarray(0, take), off);
        off += take;
        if (off === n) break;
      }
      return out;
    }
    take(n) {
      if (this.len < n) return null;
      const out = new Uint8Array(n);
      let off = 0;
      while (off < n) {
        const first = this.chunks[0];
        const need = n - off;
        if (first.length <= need) {
          out.set(first, off);
          off += first.length;
          this.chunks.shift();
        } else {
          out.set(first.subarray(0, need), off);
          this.chunks[0] = first.subarray(need);
          off += need;
        }
      }
      this.len -= n;
      return out;
    }
  }

  let q = new ByteQueue();
  let state = "VERSION";
  let secCount = 0;
  let initNameLen = 0;
  let pendingRects = 0;
  let curRect = null;
  let skipBytes = 0;

  function sendBytes(arr) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(new Uint8Array(arr));
    }
  }

  function requestFrame(incremental) {
    sendBytes([
      3, incremental ? 1 : 0,
      0, 0, 0, 0,
      (fbW >> 8) & 255, fbW & 255,
      (fbH >> 8) & 255, fbH & 255,
    ]);
  }

  function sendPointer(x, y, mask) {
    if (!ws || ws.readyState !== WebSocket.OPEN || state !== "MAIN") return;
    x = Math.max(0, Math.min(fbW - 1, Math.round(x)));
    y = Math.max(0, Math.min(fbH - 1, Math.round(y)));
    sendBytes([5, mask & 255, (x >> 8) & 255, x & 255, (y >> 8) & 255, y & 255]);
  }

  function sendKey(keysym, down) {
    if (!ws || ws.readyState !== WebSocket.OPEN || state !== "MAIN") return;
    sendBytes([
      4, down ? 1 : 0, 0, 0,
      (keysym >>> 24) & 255, (keysym >>> 16) & 255,
      (keysym >>> 8) & 255, keysym & 255,
    ]);
  }

  function pump() {
    while (true) {
      if (skipBytes > 0) {
        if (q.len < skipBytes) return;
        q.take(skipBytes);
        skipBytes = 0;
      }

      if (state === "VERSION") {
        const b = q.take(12);
        if (!b) return;
        sendBytes(Array.from("RFB 003.008\\n").map(c => c.charCodeAt(0)));
        state = "SEC_COUNT";
      } else if (state === "SEC_COUNT") {
        const b = q.take(1);
        if (!b) return;
        secCount = b[0];
        if (secCount === 0) { setStatus("VNC handshake rejected", "err"); ws.close(); return; }
        state = "SEC_LIST";
      } else if (state === "SEC_LIST") {
        const b = q.take(secCount);
        if (!b) return;
        sendBytes([1]); // SecurityType None (loopback only)
        state = "SEC_RESULT";
      } else if (state === "SEC_RESULT") {
        const b = q.take(4);
        if (!b) return;
        const ok = (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3];
        if (ok !== 0) { setStatus("VNC auth failed", "err"); ws.close(); return; }
        sendBytes([1]); // ClientInit shared=1
        state = "SERVER_INIT";
      } else if (state === "SERVER_INIT") {
        const b = q.take(24);
        if (!b) return;
        const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
        fbW = dv.getUint16(0);
        fbH = dv.getUint16(2);
        initNameLen = dv.getUint32(20);
        state = "SERVER_NAME";
      } else if (state === "SERVER_NAME") {
        const b = q.take(initNameLen);
        if (!b) return;
        canvas.width = fbW;
        canvas.height = fbH;
        // SetPixelFormat: 32bpp, depth 24, LE, true-color, RGBA byte order (R=0,G=8,B=16)
        sendBytes([0, 0, 0, 0, 32, 24, 0, 1, 0, 255, 0, 255, 0, 255, 0, 8, 16, 0, 0, 0]);
        // SetEncodings: Raw (0), DesktopSize (-223 = 0xFFFFFF21)
        sendBytes([2, 0, 0, 2, 0, 0, 0, 0, 0xff, 0xff, 0xff, 0x21]);
        state = "MAIN";
        setStatus(`Live • ${fbW}×${fbH}`, "ok");
        requestFrame(false);
      } else if (state === "MAIN") {
        const p = q.peek(1);
        if (!p) return;
        const msg = p[0];
        if (msg === 0) {
          const hdr = q.take(4);
          if (!hdr) return;
          pendingRects = (hdr[2] << 8) | hdr[3];
          state = pendingRects > 0 ? "RECT_HDR" : "MAIN";
          if (pendingRects === 0) setTimeout(() => requestFrame(true), 45);
        } else if (msg === 1) {
          const hdr = q.take(6);
          if (!hdr) return;
          const colors = (hdr[4] << 8) | hdr[5];
          skipBytes = colors * 6;
        } else if (msg === 2) {
          q.take(1);
        } else if (msg === 3) {
          const hdr = q.take(8);
          if (!hdr) return;
          const dv = new DataView(hdr.buffer, hdr.byteOffset, hdr.byteLength);
          skipBytes = dv.getUint32(4);
        } else {
          setStatus(`Unknown RFB msg ${msg}`, "err");
          ws.close();
          return;
        }
      } else if (state === "RECT_HDR") {
        const b = q.take(12);
        if (!b) return;
        const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
        curRect = {
          x: dv.getUint16(0),
          y: dv.getUint16(2),
          w: dv.getUint16(4),
          h: dv.getUint16(6),
          enc: dv.getInt32(8),
        };
        if (curRect.enc === -223) {
          fbW = curRect.w;
          fbH = curRect.h;
          canvas.width = fbW;
          canvas.height = fbH;
          setStatus(`Live • ${fbW}×${fbH}`, "ok");
          pendingRects--;
          if (pendingRects === 0) {
            state = "MAIN";
            requestFrame(false);
          }
        } else if (curRect.enc === 0) {
          state = "RECT_RAW";
        } else {
          setStatus(`Unsupported enc ${curRect.enc}`, "err");
          ws.close();
          return;
        }
      } else if (state === "RECT_RAW") {
        const need = curRect.w * curRect.h * 4;
        const raw = q.take(need);
        if (!raw) return;
        if (curRect.w > 0 && curRect.h > 0) {
          const clamped = new Uint8ClampedArray(raw.buffer, raw.byteOffset, raw.byteLength);
          for (let i = 3; i < clamped.length; i += 4) clamped[i] = 255;
          const img = new ImageData(clamped, curRect.w, curRect.h);
          ctx.putImageData(img, curRect.x, curRect.y);
        }
        pendingRects--;
        if (pendingRects === 0) {
          state = "MAIN";
          setTimeout(() => requestFrame(true), 45);
        } else {
          state = "RECT_HDR";
        }
      }
    }
  }

  function connect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (ws) { try { ws.close(); } catch (_) {} }
    q = new ByteQueue();
    state = "VERSION";
    pendingRects = 0;
    skipBytes = 0;
    setStatus("Connecting to FeatherOS VM...");
    ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => setStatus("Handshaking with QEMU...");
    ws.onmessage = (ev) => { q.push(ev.data); pump(); };
    ws.onerror = () => setStatus("Waiting for QEMU VNC...", "err");
    ws.onclose = () => {
      setStatus("Disconnected — retrying...", "err");
      reconnectTimer = setTimeout(connect, 2000);
    };
  }

  function canvasCoords(ev) {
    const r = canvas.getBoundingClientRect();
    return {
      x: ((ev.clientX - r.left) / r.width) * fbW,
      y: ((ev.clientY - r.top) / r.height) * fbH,
    };
  }

  canvas.addEventListener("contextmenu", e => e.preventDefault());
  canvas.addEventListener("mousemove", e => {
    const c = canvasCoords(e);
    sendPointer(c.x, c.y, btnMask);
  });
  canvas.addEventListener("mousedown", e => {
    canvas.focus();
    const bit = e.button === 0 ? 1 : (e.button === 1 ? 2 : (e.button === 2 ? 4 : 0));
    btnMask |= bit;
    const c = canvasCoords(e);
    sendPointer(c.x, c.y, btnMask);
  });
  canvas.addEventListener("mouseup", e => {
    const bit = e.button === 0 ? 1 : (e.button === 1 ? 2 : (e.button === 2 ? 4 : 0));
    btnMask &= ~bit;
    const c = canvasCoords(e);
    sendPointer(c.x, c.y, btnMask);
  });
  canvas.addEventListener("wheel", e => {
    e.preventDefault();
    const bit = e.deltaY < 0 ? 8 : 16;
    const c = canvasCoords(e);
    sendPointer(c.x, c.y, btnMask | bit);
    sendPointer(c.x, c.y, btnMask);
  }, { passive: false });

  const SPECIAL_KEYS = {
    Backspace: 0xff08, Tab: 0xff09, Enter: 0xff0d, Escape: 0xff1b,
    Insert: 0xff63, Delete: 0xffff, Home: 0xff50, End: 0xff57,
    PageUp: 0xff55, PageDown: 0xff56,
    ArrowLeft: 0xff51, ArrowUp: 0xff52, ArrowRight: 0xff53, ArrowDown: 0xff54,
    F1: 0xffbe, F2: 0xffbf, F3: 0xffc0, F4: 0xffc1, F5: 0xffc2, F6: 0xffc3,
    F7: 0xffc4, F8: 0xffc5, F9: 0xffc6, F10: 0xffc7, F11: 0xffc8, F12: 0xffc9,
    Shift: 0xffe1, Control: 0xffe3, Alt: 0xffe9, Meta: 0xffeb,
  };

  function keyToSym(e) {
    if (SPECIAL_KEYS[e.key]) return SPECIAL_KEYS[e.key];
    if (e.key.length === 1) {
      const code = e.key.charCodeAt(0);
      if (code >= 0x20 && code <= 0x7e) return code;
    }
    return null;
  }

  window.addEventListener("keydown", e => {
    const sym = keyToSym(e);
    if (sym !== null) { e.preventDefault(); sendKey(sym, true); }
  });
  window.addEventListener("keyup", e => {
    const sym = keyToSym(e);
    if (sym !== null) { e.preventDefault(); sendKey(sym, false); }
  });

  document.getElementById("btnSuper").onclick = () => {
    sendKey(0xffeb, true); setTimeout(() => sendKey(0xffeb, false), 80);
  };
  document.getElementById("btnCad").onclick = () => {
    sendKey(0xffe3, true); sendKey(0xffe9, true); sendKey(0xffff, true);
    setTimeout(() => { sendKey(0xffff, false); sendKey(0xffe9, false); sendKey(0xffe3, false); }, 100);
  };
  document.getElementById("btnReconnect").onclick = connect;
  document.getElementById("btnFull").onclick = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  };

  connect();
})();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="FeatherOS Live Web VNC Console")
    parser.add_argument("--http-port", type=int, default=8765)
    parser.add_argument("--ws-port", type=int, default=5701)
    args = parser.parse_args()

    html_bytes = HTML_TEMPLATE.replace("__WS_PORT__", str(args.ws_port)).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(html_bytes)
            else:
                self.send_error(404)

        def log_message(self, format: str, *log_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), Handler)
    print(
        f"FeatherOS Web Console listening on http://127.0.0.1:{args.http_port} "
        f"(QEMU WebSocket VNC ws://127.0.0.1:{args.ws_port})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
