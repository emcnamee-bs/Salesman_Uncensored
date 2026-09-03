// MerchMarket Astroturfer — popup. Loads replies-DATE.json, runs the queue.
// Keep DELAY_MIN/DELAY_MAX in sync with config/settings.json limits.
const DELAY_MIN = 120; // seconds
const DELAY_MAX = 600; // seconds

let queue = [];       // entries from the replies file
let running = false;
let pausedOn = -1;    // index of entry that failed (not_found/error)

const $file = document.getElementById("file");
const $preview = document.getElementById("preview");
const $start = document.getElementById("start");
const $status = document.getElementById("status");
const $queue = document.getElementById("queue");

function render() {
  $queue.innerHTML = "";
  queue.forEach((e, i) => {
    const div = document.createElement("div");
    div.className = "entry" + (e._done ? " done" : "") + (i === pausedOn ? " paused-on" : "");
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${e.subreddit} · ${e.comment_id} · matched: ${e.matched_keywords.join(", ")}`;
    const link = document.createElement("a");
    link.href = e.permalink;
    link.target = "_blank";
    link.textContent = "open thread";
    meta.appendChild(document.createTextNode("  "));
    meta.appendChild(link);
    if (e._status) {
      const st = document.createElement("span");
      st.className = "meta";
      st.textContent = ` — ${e._status}`;
      meta.appendChild(st);
    }
    const reply = document.createElement("div");
    reply.className = "reply-text";
    reply.textContent = e.reply;
    div.appendChild(meta);
    div.appendChild(reply);
    $queue.appendChild(div);
  });
}

function setStatus(text) { $status.textContent = text; }

async function loadFromStorage() {
  const stored = await chrome.storage.local.get("astroturfQueue");
  if (stored.astroturfQueue && stored.astroturfQueue.length) {
    queue = stored.astroturfQueue;
    render();
    setStatus(`${queue.length} entries loaded from last session`);
  }
}

async function persist() {
  await chrome.storage.local.set({ astroturfQueue: queue });
}

$file.addEventListener("change", async () => {
  const f = $file.files[0];
  if (!f) return;
  try {
    const parsed = JSON.parse(await f.text());
    if (!Array.isArray(parsed)) throw new Error("expected a JSON array");
    queue = parsed.filter((e) => e && e.comment_id && e.reply);
    pausedOn = -1;
    await persist();
    render();
    setStatus(`${queue.length} entries loaded`);
  } catch (err) {
    setStatus(`load failed: ${err.message}`);
  }
});

function randomDelay() {
  return Math.floor(DELAY_MIN + Math.random() * (DELAY_MAX - DELAY_MIN));
}

async function waitSeconds(sec) {
  for (let remaining = sec; remaining > 0; remaining--) {
    setStatus(`waiting ${remaining}s until next post…`);
    await new Promise((r) => setTimeout(r, 1000));
  }
}

function activeTab() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => resolve(tabs[0]));
  });
}

async function sendToTab(tabId, message) {
  return new Promise((resolve) => {
    try {
      chrome.tabs.sendMessage(tabId, message, (resp) => {
        if (chrome.runtime.lastError) resolve({ ok: false, status: "error", detail: chrome.runtime.lastError.message });
        else resolve(resp || { ok: false, status: "error", detail: "no response" });
      });
    } catch (e) {
      resolve({ ok: false, status: "error", detail: e.message });
    }
  });
}

async function postEntry(entry) {
  const tab = await activeTab();
  // Real navigation to the thread page — never inject into stale DOM.
  await new Promise((resolve) => {
    chrome.tabs.update(tab.id, { url: entry.permalink }, () => resolve());
  });
  // Wait for load + old-reddit render before messaging the content script.
  await waitSeconds(4);
  const resp = await sendToTab(tab.id, {
    type: "astroturf_post",
    comment_id: entry.comment_id,
    text: entry.reply,
    preview: $preview.checked,
  });
  return resp;
}

$start.addEventListener("click", async () => {
  if (running) return;
  if (!queue.length) { setStatus("load a replies file first"); return; }
  running = true;
  pausedOn = -1;
  for (let i = 0; i < queue.length; i++) {
    const entry = queue[i];
    if (entry._done) continue;
    try {
      setStatus(`posting ${i + 1}/${queue.length} (${entry.subreddit})…`);
      const resp = await postEntry(entry);
      entry._status = resp.status || "error";
      entry._done = true;
      render();
      if (resp.status === "not_found" || resp.status === "error") {
        pausedOn = i;
        setStatus(`paused on entry ${i + 1}: ${resp.status}${resp.detail ? " — " + resp.detail : ""}`);
        running = false;
        await persist();
        return;
      }
    } catch (err) {
      entry._status = `error: ${err.message}`;
      pausedOn = i;
      setStatus(`paused on entry ${i + 1}: ${err.message}`);
      running = false;
      await persist();
      return;
    }
    if (i < queue.length - 1) {
      const d = randomDelay();
      await waitSeconds(d);
    }
  }
  running = false;
  setStatus("queue complete");
  await persist();
});

loadFromStorage();
