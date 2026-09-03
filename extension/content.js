// MerchMarket Astroturfer — content script for old.reddit.com thread pages.
// Finds the comment by its Reddit ID, clicks Reply, types with human pacing, submits.
//
// SELECTORS below target old-reddit DOM. If Reddit changes markup, update them
// here only (verified via the README manual checklist).

const SELECTORS = {
  // Comment container: old reddit renders each comment as <div class="thing" id="t1_<id>">
  commentById: (id) => `#t1_${id}`,
  // The "reply" action link inside a comment's entry block.
  replyLink: ".commentarea",
  // Fallbacks if the primary selector ever changes:
  replyLinkFallbacks: ['a[href*="/reply/"]', 'a.bylink'],
  // The textarea that appears after clicking Reply (old reddit usertext form).
  replyBox: "textarea.usertext-body",
  replyBoxFallbacks: ["form.usertext textarea"],
  // Submit button of the usertext form.
  submitButton: "form.usertext .save, form.usertext button[type='submit']",
  // Moderation-hold notice text (spec: "post pending" detection).
  moderationTexts: ["awaiting moderation", "pending review", "your submission is awaiting"],
};

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function jitter(min, max) { return min + Math.floor(Math.random() * (max - min)); }

async function waitFor(selector, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const el = document.querySelector(selector);
    if (el) return el;
    await sleep(250);
  }
  return null;
}

function firstExisting(selectors) {
  for (const s of selectors) {
    const el = document.querySelector(s);
    if (el) return el;
  }
  return null;
}

async function typeHuman(box, text) {
  box.focus();
  await sleep(jitter(300, 900)); // human thinks before typing
  for (const ch of text) {
    box.value += ch;
    box.dispatchEvent(new Event("input", { bubbles: true }));
    let delay = jitter(25, 110);
    if (".!?,".includes(ch)) delay += jitter(120, 400); // micro-pause at punctuation
    await sleep(delay);
  }
}

async function handlePost(message) {
  const commentEl = document.querySelector(SELECTORS.commentById(message.comment_id));
  if (!commentEl) return { ok: false, status: "not_found", detail: `no element #t1_${message.comment_id}` };

  // Scroll into view like a human would.
  commentEl.scrollIntoView({ block: "center" });
  await sleep(jitter(600, 1500));

  const replyLink = firstExisting([SELECTORS.replyLink, ...SELECTORS.replyLinkFallbacks]);
  if (!replyLink) return { ok: false, status: "error", detail: "reply link not found" };
  replyLink.click();
  await sleep(jitter(500, 1200));

  const box = firstExisting([SELECTORS.replyBox, ...SELECTORS.replyBoxFallbacks]);
  if (!box) return { ok: false, status: "error", detail: "reply textarea not found" };

  await typeHuman(box, message.text);
  await sleep(jitter(800, 2000)); // read it back before submitting

  if (message.preview) {
    return { ok: true, status: "previewed" };
  }

  const submit = firstExisting([SELECTORS.submitButton]);
  if (!submit) return { ok: false, status: "error", detail: "submit button not found" };
  submit.click();

  // Wait for either our comment to appear or a moderation notice.
  await sleep(2500);
  const bodyText = (document.body.innerText || "").toLowerCase();
  if (SELECTORS.moderationTexts.some((t) => bodyText.includes(t))) {
    return { ok: true, status: "pending_moderation" };
  }
  // Old reddit re-renders the thread; our new comment should now exist.
  const all = document.body.innerText || "";
  if (all.toLowerCase().includes(message.text.slice(0, 40).toLowerCase())) {
    return { ok: true, status: "posted" };
  }
  // Not conclusive — treat as posted-pending to be safe (counts against cap either way per spec).
  return { ok: true, status: "pending_moderation", detail: "confirmation not detected; check thread manually" };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "astroturf_post") return false;
  handlePost(message).then(sendResponse);
  return true; // async response
});
