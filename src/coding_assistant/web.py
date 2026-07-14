"""Browser interface for the coding assistant.

Run with: uv run coding-assistant-web
Then open http://127.0.0.1:8000 in a browser.

Notes:
- Conversations live in memory: they disappear when the server stops.
- File deletions are off unless the "allow delete" toggle is on.
- Click Send again while a reply is generating to stop it early.

"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from rich.console import Console

from coding_assistant.deps import AgentDeps
from coding_assistant.main import build_agent

app = FastAPI(title="coding assistant")

_console = Console()
_agent = build_agent()

# conversation_id -> {"title", "time", "history", "display"}
_conversations: dict[str, dict] = {}

# conversation_id -> the in-flight agent.run() task, so /chat/{cid}/stop
# can cancel it while the client's original /chat request is still open.
_running: dict[str, asyncio.Task] = {}

_PLAN_NOTE = (
    "(Planning mode is ON: explore the project and present a design. "
    "Do not create, modify, or delete any files. Wait for approval.)\n"
)
_EXPLAIN_NOTE = (
    "(Extended explanations are ON: walk through any code you write or "
    "read line by line, in plain language.)\n"
)


class ChatRequest(BaseModel):
    """One chat message plus the UI toggles that apply to it."""

    message: str
    conversation_id: str | None = None
    plan: bool = False
    explain: bool = False
    reasoning: str = "medium"
    allow_delete: bool = False


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serve the single-page chat UI."""
    return _PAGE


@app.get("/conversations")
async def list_conversations() -> list[dict]:
    """List conversations for the history panel, newest first."""
    return [
        {"id": cid, "title": c["title"], "time": c["time"]}
        for cid, c in reversed(list(_conversations.items()))
    ]


@app.get("/conversations/{cid}")
async def get_conversation(cid: str) -> dict:
    """Return the display messages of one conversation."""
    conv = _conversations.get(cid)
    if conv is None:
        return {"display": []}
    return {"display": conv["display"]}


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    """Run one agent request and return the reply with usage and events."""
    # The client generates the id up front (for a new conversation too) so
    # it can immediately target /chat/{cid}/stop while this call is pending.
    cid = req.conversation_id or uuid.uuid4().hex[:8]

    # One request at a time per conversation: a second one would overwrite
    # the running task in _running and Stop could miss the first request.
    if cid in _running:
        return {
            "conversation_id": cid,
            "title": _conversations[cid]["title"],
            "reply": "_Another request is still running in this "
            "conversation. Stop it or wait for it to finish._",
            "usage": "",
            "events": [],
        }

    conv = _conversations.get(cid)
    if conv is None:
        conv = {
            "title": req.message[:48],
            "time": datetime.now().strftime("%H:%M"),
            "history": None,
            "display": [],
        }
        _conversations[cid] = conv

    # Reasoning effort: reuse the @low/@high capability by tagging.
    message = req.message
    if req.reasoning == "low":
        message = "@low " + message
    elif req.reasoning == "high":
        message = "@high " + message

    # Plan mode: mechanical lock lives in deps; the note informs the model.
    if req.plan:
        message = _PLAN_NOTE + message
    if req.explain:
        message = _EXPLAIN_NOTE + message

    # Fresh deps per request: no state shared between concurrent chats.
    # The web UI cannot prompt mid-request, so the "allow delete" toggle
    # is the deletion consent; with it off, delete_file refuses to act.
    deps = AgentDeps(
        console=_console,
        plan_mode=req.plan,
        confirm_delete=(lambda _path: True) if req.allow_delete else None,
    )

    task = asyncio.ensure_future(
        _agent.run(message, message_history=conv["history"], deps=deps)
    )
    _running[cid] = task

    try:
        result = await task
    except asyncio.CancelledError:
        # Keep the stopped exchange visible when the conversation is
        # reopened from the history panel.
        conv["display"].append({"role": "user", "text": req.message})
        conv["display"].append({"role": "bot", "text": "_Stopped by user._"})
        return {
            "conversation_id": cid,
            "title": conv["title"],
            "reply": "_Stopped by user._",
            "usage": "",
            "events": list(deps.events),
        }
    except Exception as exc:  # noqa: BLE001 - report instead of crashing
        return {
            "conversation_id": cid,
            "title": conv["title"],
            "reply": f"Request failed: {exc}. Please try again.",
            "usage": "",
            "events": list(deps.events),
        }
    finally:
        _running.pop(cid, None)

    conv["history"] = result.all_messages()
    conv["display"].append({"role": "user", "text": req.message})
    conv["display"].append({"role": "bot", "text": result.output})

    return {
        "conversation_id": cid,
        "title": conv["title"],
        "reply": result.output,
        "usage": str(result.usage()),
        "events": list(deps.events),
    }


@app.post("/chat/{cid}/stop")
async def stop_chat(cid: str) -> dict:
    """Cancel the in-flight request of a conversation, if any."""
    task = _running.get(cid)
    if task is not None and not task.done():
        task.cancel()
        return {"stopped": True}
    return {"stopped": False}


_PAGE = """<!doctype html>
<html lang="en" data-theme="night">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>coding assistant</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.0/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.8/purify.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300..700&family=Figtree:wght@300..700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  [data-theme="night"] {
    --bg:#0b1220; --surface:#131e33;
    --ink:#bcd7ff; --ink-soft:#7f9fce;
    --accent:#7db4ff; --line:rgba(125,180,255,.15);
  }
  [data-theme="wine"] {
    --bg:#1c0c16; --surface:#2d1322;
    --ink:#fce7f0; --ink-soft:#c493a8;
    --accent:#f6bed8; --line:rgba(240,160,195,.15);
  }

  * { box-sizing:border-box; scrollbar-width:thin;
      scrollbar-color:var(--accent) transparent; }
  ::-webkit-scrollbar { width:9px; height:9px; }
  ::-webkit-scrollbar-track { background:transparent; }
  ::-webkit-scrollbar-thumb { background:var(--line); border-radius:999px;
    border:2px solid transparent; background-clip:padding-box; }
  ::-webkit-scrollbar-thumb:hover { background:var(--accent);
    border:2px solid transparent; background-clip:padding-box; }

  html, body { height:100%; }
  body {
    margin:0; font-family:"Figtree",sans-serif; color:var(--ink);
    background:var(--bg);
    display:flex; flex-direction:column;
    transition:background .6s ease, color .4s ease;
  }

  header {
    display:flex; align-items:center; justify-content:space-between;
    flex-wrap:wrap; gap:10px; padding:14px 22px;
    border-bottom:1px solid var(--line);
  }
  header h1 { font-family:"Fraunces",serif; font-weight:500; font-size:24px;
    letter-spacing:.3px; margin:0; color:var(--ink);
    text-transform:lowercase; }

  .controls { display:flex; align-items:center; gap:10px;
              flex-wrap:wrap; min-width:0; }
  .seg { display:flex; border:1px solid var(--line); border-radius:999px;
         overflow:hidden; font-size:12.5px; }
  .seg span { color:var(--ink-soft); padding:8px 10px 8px 14px; }
  .seg button { font-family:inherit; font-size:12.5px; letter-spacing:.4px;
    color:var(--ink-soft); background:transparent; border:0;
    padding:8px 14px; cursor:pointer; transition:all .2s; }
  .seg button.active { color:var(--bg); background:var(--accent);
                       font-weight:600; }
  .seg button:hover:not(.active) { color:var(--ink); }
  .toggle { font-family:inherit; font-size:12.5px; letter-spacing:.4px;
    color:var(--ink); background:var(--surface); border:1px solid var(--line);
    border-radius:999px; padding:8px 16px; cursor:pointer; transition:all .2s; }
  .toggle:hover { background:var(--line); }
  .toggle.active { color:var(--bg); background:var(--accent);
                   border-color:var(--accent); font-weight:600; }
  .swatches { display:flex; gap:8px; padding:5px;
              border:1px solid var(--line); border-radius:999px; }
  .swatch { width:22px; height:22px; border-radius:50%; cursor:pointer;
    border:2px solid transparent; transition:transform .2s,border-color .2s; }
  .swatch:hover { transform:scale(1.12); }
  .swatch.night { background:#7db4ff; }
  .swatch.wine  { background:#f6bed8; }
  [data-theme="night"] .swatch.night,
  [data-theme="wine"]  .swatch.wine { border-color:var(--ink); }

  main { flex:1; display:flex; min-height:0; }

  nav { width:232px; flex-shrink:0; padding:16px 12px;
    border-right:1px solid var(--line); display:flex; flex-direction:column;
    gap:6px; background:var(--surface); transition:width .35s ease; }
  aside { width:262px; flex-shrink:0; padding:16px 14px;
    border-left:1px solid var(--line); background:var(--surface);
    display:flex; flex-direction:column; gap:8px; overflow-y:auto;
    transition:width .35s ease; }
  .panel-head { display:flex; align-items:center;
                justify-content:space-between; padding:0 2px 6px; }
  .fold { width:26px; height:26px; flex-shrink:0; cursor:pointer;
    display:flex; align-items:center; justify-content:center;
    color:var(--ink-soft); background:var(--surface);
    border:1px solid var(--line); border-radius:8px; font-size:12px;
    transition:transform .35s ease,color .2s; }
  .fold:hover { color:var(--ink); }
  .foldable { display:flex; flex-direction:column; gap:6px; min-height:0;
              overflow-y:auto; }
  nav.collapsed, aside.collapsed { width:46px; padding:16px 8px; }
  nav.collapsed .foldable, aside.collapsed .foldable,
  nav.collapsed .navlabel, aside.collapsed .loglabel { display:none; }
  nav.collapsed .panel-head, aside.collapsed .panel-head
    { justify-content:center; }
  nav.collapsed .fold, aside.collapsed .fold { transform:rotate(180deg); }

  .newchat { font-family:inherit; font-size:13px; font-weight:600;
    color:var(--bg); background:var(--accent); border:0; border-radius:12px;
    padding:10px; cursor:pointer; margin-bottom:10px; transition:filter .2s; }
  .newchat:hover { filter:brightness(1.1); }
  .navlabel, .loglabel { font-size:11px; letter-spacing:1.5px;
    text-transform:uppercase; color:var(--ink-soft); padding:0 4px; }
  .conv { font-size:13.5px; color:var(--ink); padding:9px 10px;
    border-radius:10px; cursor:pointer; white-space:nowrap; overflow:hidden;
    text-overflow:ellipsis; transition:background .2s; flex-shrink:0; }
  .conv:hover { background:var(--surface); }
  .conv.active { background:var(--surface); border:1px solid var(--line); }
  .conv time { display:block; font-size:11px; color:var(--ink-soft); }

  #chat { flex:1; overflow-y:auto; padding:20px 24px; min-width:0; }
  .lane { max-width:44rem; margin:0 auto; display:flex;
          flex-direction:column; gap:4px; }
  .msg { padding:13px 17px; border-radius:16px; line-height:1.65;
    font-size:14.5px; border:1px solid var(--line);
    animation:rise .45s ease both; overflow-wrap:break-word; }
  .user { align-self:flex-end; max-width:85%; background:var(--surface);
          border-color:var(--accent);
          border-bottom-right-radius:6px; white-space:pre-wrap; }
  .bot { align-self:flex-start; max-width:92%; background:var(--surface);
         border-bottom-left-radius:6px; backdrop-filter:blur(6px); }
  @keyframes rise { from { opacity:0; transform:translateY(10px); }
                    to { opacity:1; transform:none; } }
  .meta { align-self:flex-start; font-size:11.5px; color:var(--ink-soft);
          letter-spacing:.4px; padding:2px 6px 14px; }

  pre { background:var(--surface); border:1px solid var(--line);
    border-radius:12px; padding:13px 15px; overflow-x:auto;
    font-family:"JetBrains Mono",monospace; font-size:12.5px;
    line-height:1.6; margin:10px 0 4px; }
  code { font-family:"JetBrains Mono",monospace; color:var(--accent); }
  pre code { color:var(--ink); }

  .log { font-family:"JetBrains Mono",monospace; font-size:11.5px;
    line-height:1.5; color:var(--ink); border:1px solid var(--line);
    border-left:3px solid var(--accent); border-radius:8px; padding:8px 10px;
    background:var(--surface); animation:rise .4s ease both; flex-shrink:0; }
  .log time { color:var(--ink-soft); display:block; font-size:10.5px; }

  .composer { padding:12px 24px 20px; border-top:1px solid var(--line); }
  .composer-inner { max-width:44rem; margin:0 auto; display:flex; gap:10px;
    background:var(--surface); border:1px solid var(--line);
    border-radius:18px; padding:9px 9px 9px 16px; backdrop-filter:blur(8px); }
  textarea { flex:1; border:0; background:transparent; resize:none;
    color:var(--ink); font-family:inherit; font-size:14.5px; line-height:1.5;
    outline:none; padding-top:8px; }
  textarea::placeholder { color:var(--ink-soft); }
  .send { align-self:flex-end; border:0; border-radius:12px;
    padding:11px 20px; cursor:pointer; font-family:inherit; font-size:13.5px;
    font-weight:600; color:var(--bg); background:var(--accent); letter-spacing:.4px;
    transition:transform .15s ease,filter .2s; }
  .send:hover { transform:translateY(-1px); filter:brightness(1.12); }
  .send:disabled { opacity:.5; }
  .hint { max-width:44rem; margin:7px auto 0; font-size:11px;
    color:var(--ink-soft); text-align:center; letter-spacing:.4px; }

  @media (max-width:1150px) { nav { width:188px; } aside { width:216px; } }
  @media (max-width:920px) {
    .seg span { display:none; }
    .seg button { padding:8px 11px; }
    .toggle { padding:8px 12px; }
    nav:not(.collapsed), aside:not(.collapsed) { width:46px; padding:16px 8px; }
    nav:not(.collapsed) .foldable, aside:not(.collapsed) .foldable,
    nav:not(.collapsed) .navlabel, aside:not(.collapsed) .loglabel
      { display:none; }
    nav:not(.collapsed) .panel-head, aside:not(.collapsed) .panel-head
      { justify-content:center; }
  }
  @media (max-width:680px) {
    header { padding:10px 12px; }
    header h1 { font-size:20px; }
    #chat { padding:14px 12px; }
    .composer { padding:10px 12px 14px; }
    nav, aside { display:none; }
  }
</style>
</head>
<body>

<header>
  <h1>coding assistant</h1>
  <div class="controls">
    <div class="seg" title="Reasoning effort">
      <span>reasoning</span>
      <button data-level="low" onclick="setReasoning(this)">low</button>
      <button data-level="medium" class="active" onclick="setReasoning(this)">medium</button>
      <button data-level="high" onclick="setReasoning(this)">high</button>
    </div>
    <button class="toggle" id="plan" onclick="this.classList.toggle('active')">plan mode</button>
    <button class="toggle" id="explain" onclick="this.classList.toggle('active')">explain</button>
    <button class="toggle" id="allowdel" title="Let the agent delete files (off by default)"
      onclick="this.classList.toggle('active')">allow delete</button>
    <div class="swatches" title="Theme">
      <div class="swatch night" onclick="setTheme('night')" title="night"></div>
      <div class="swatch wine" onclick="setTheme('wine')" title="wine"></div>
    </div>
  </div>
</header>

<main>
  <nav id="nav">
    <div class="panel-head">
      <div class="navlabel">history</div>
      <button class="fold" onclick="fold('nav')" title="Hide/show history">&#10094;</button>
    </div>
    <div class="foldable">
      <button class="newchat" onclick="newChat()">+ new conversation</button>
      <div id="convlist"></div>
    </div>
  </nav>

  <div id="chat"><div class="lane" id="lane"></div></div>

  <aside id="logpanel">
    <div class="panel-head">
      <div class="loglabel">activity log</div>
      <button class="fold" onclick="fold('logpanel')" title="Hide/show log">&#10095;</button>
    </div>
    <div class="foldable" id="logbody"></div>
  </aside>
</main>

<div class="composer">
  <div class="composer-inner">
    <textarea id="box" rows="2" placeholder="Write a request&hellip;"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey&&!sending){send(event);}"></textarea>
    <button class="send" id="btn" onclick="send(event)">Send</button>
  </div>
  <div class="hint">Enter &mdash; send &middot; Shift+Enter &mdash; new line</div>
</div>

<script>
let currentId = null;
let reasoning = 'medium';
let sending = false;

const lane = document.getElementById('lane');
const box = document.getElementById('box');
const btn = document.getElementById('btn');
const logbody = document.getElementById('logbody');
const convlist = document.getElementById('convlist');

function setTheme(name) {
  document.documentElement.setAttribute('data-theme', name);
}
function fold(id) {
  document.getElementById(id).classList.toggle('collapsed');
}
function setReasoning(btnEl) {
  btnEl.parentElement.querySelectorAll('button')
       .forEach(function (b) { b.classList.remove('active'); });
  btnEl.classList.add('active');
  reasoning = btnEl.dataset.level;
}

// Markdown -> safe HTML. DOMPurify strips scripts and event handlers:
// model output is untrusted (a read file can smuggle HTML into it).
function render(md) {
  return DOMPurify.sanitize(marked.parse(md));
}

function addMsg(cls, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + cls;
  if (cls === 'user') { div.textContent = text; }
  else { div.innerHTML = render(text); }
  lane.appendChild(div);
  document.getElementById('chat').scrollTop = 1e9;
  return div;
}
function addMeta(text) {
  const div = document.createElement('div');
  div.className = 'meta';
  div.textContent = text;
  lane.appendChild(div);
}
function addLog(text) {
  const div = document.createElement('div');
  div.className = 'log';
  const t = document.createElement('time');
  t.textContent = new Date().toLocaleTimeString();
  div.appendChild(t);
  div.appendChild(document.createTextNode(text));
  logbody.appendChild(div);
  logbody.scrollTop = 1e9;
}

async function refreshConvs() {
  const r = await fetch('/conversations');
  const items = await r.json();
  convlist.innerHTML = '';
  items.forEach(function (c) {
    const div = document.createElement('div');
    div.className = 'conv' + (c.id === currentId ? ' active' : '');
    div.textContent = c.title;
    const t = document.createElement('time');
    t.textContent = c.time;
    div.appendChild(t);
    div.onclick = function () { openConv(c.id); };
    convlist.appendChild(div);
  });
}

async function openConv(cid) {
  currentId = cid;
  const r = await fetch('/conversations/' + cid);
  const data = await r.json();
  lane.innerHTML = '';
  data.display.forEach(function (m) {
    addMsg(m.role === 'user' ? 'user' : 'bot', m.text);
  });
  refreshConvs();
}

function newChat() {
  currentId = null;
  lane.innerHTML = '';
  logbody.innerHTML = '';
  refreshConvs();
  box.focus();
}

async function send(event) {
  event.preventDefault();
  if (sending) { stopRequest(); return; }

  const text = box.value.trim();
  if (!text) return;
  // Generated client-side (not by the server) so the id is known before
  // the request even starts, letting Stop target it immediately.
  if (!currentId) currentId = crypto.randomUUID();
  const cid = currentId;

  sending = true;
  btn.textContent = 'Stop';
  box.value = '';
  addMsg('user', text);
  const waiting = addMsg('bot', '<i>thinking&hellip;</i>');
  try {
    const r = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        message: text,
        conversation_id: cid,
        plan: document.getElementById('plan').classList.contains('active'),
        explain: document.getElementById('explain').classList.contains('active'),
        allow_delete: document.getElementById('allowdel').classList.contains('active'),
        reasoning: reasoning,
      }),
    });
    const data = await r.json();
    currentId = data.conversation_id;
    waiting.innerHTML = render(data.reply);
    if (data.usage) addMeta(data.usage);
    (data.events || []).forEach(addLog);
    refreshConvs();
  } catch (e) {
    waiting.textContent = 'Connection error: ' + e;
  }
  sending = false;
  btn.textContent = 'Send';
  box.focus();
}

async function stopRequest() {
  if (!currentId) return;
  btn.disabled = true;
  try { await fetch('/chat/' + currentId + '/stop', {method: 'POST'}); }
  catch (e) { /* the pending /chat call will still time out on its own */ }
  btn.disabled = false;
}

refreshConvs();
box.focus();
</script>
</body>
</html>"""


def main() -> None:
    """Entry point: serve the web UI on localhost."""
    Path("sandbox").mkdir(exist_ok=True)
    uvicorn.run(app, host="127.0.0.1", port=8000)
