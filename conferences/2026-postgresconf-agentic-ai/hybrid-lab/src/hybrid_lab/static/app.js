const RRF_K = 60;
const STORE_KEY = "hybrid-lab-arms";
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

const state = { arms: [], selected: new Set(), matches: new Map(), answers: new Map() };
const $ = (id) => document.getElementById(id);

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of [].concat(children)) {
    if (child !== null && child !== undefined) node.append(child);
  }
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `${path} failed with ${response.status}`);
  return body;
}

function setStatus(message, isError = false) {
  const status = $("status");
  status.textContent = message;
  status.classList.toggle("error", isError);
}

/* Arms */

function savedSelection() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
    return Array.isArray(saved) ? saved : null;
  } catch {
    return null;
  }
}

function saveSelection() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify([...state.selected]));
  } catch {
    /* Private windows can refuse storage; the selection still works for this visit. */
  }
}

function armToggle(arm) {
  const input = el("input", {
    type: "checkbox",
    checked: state.selected.has(arm.stage),
    disabled: !arm.available,
    onchange: (event) => {
      if (event.target.checked) state.selected.add(arm.stage);
      else state.selected.delete(arm.stage);
      saveSelection();
    },
  });
  const classes = ["arm-toggle", arm.pitfall && "pitfall", !arm.available && "unavailable"];
  return el("label", {
    class: classes.filter(Boolean).join(" "),
    title: arm.unavailable_reason || `sql/${arm.sql_file}`,
  }, [input, el("span", { text: arm.label })]);
}

function renderArms() {
  const main = $("arms-main");
  const more = $("arms-more");
  main.replaceChildren();
  more.replaceChildren();
  for (const arm of state.arms) {
    (arm.default_on || arm.pitfall ? main : more).append(armToggle(arm));
  }
}

async function loadArms() {
  state.arms = await api("/api/arms");
  const saved = savedSelection();
  const defaults = state.arms.filter((arm) => arm.default_on).map((arm) => arm.stage);
  const available = new Set(state.arms.filter((arm) => arm.available).map((arm) => arm.stage));
  state.selected = new Set((saved || defaults).filter((stage) => available.has(stage)));
  renderArms();
}

/* Questions */

async function loadQuestions(term = "") {
  const data = await api(`/api/questions?q=${encodeURIComponent(term)}`);
  const list = $("question-matches");
  list.replaceChildren();
  for (const match of data.matches) {
    state.matches.set(match.body, match.id);
    list.append(el("option", { value: match.body }));
  }
  return data;
}

function renderDemoQuestions(demo) {
  const picks = $("demo-questions");
  picks.replaceChildren();
  for (const item of demo) {
    state.matches.set(item.body, item.id);
    picks.append(el("button", {
      type: "button", class: "pick", title: item.reason,
      onclick: () => search({ question_id: item.id }),
    }, [el("strong", { text: item.label }), el("span", { text: item.body })]));
  }
}

/* Search */

async function search(request) {
  const arms = state.arms.map((arm) => arm.stage).filter((stage) => state.selected.has(stage));
  if (!arms.length) {
    setStatus("Choose at least one arm to compare.", true);
    return;
  }
  const button = document.querySelector("#ask .primary");
  button.disabled = true;
  setStatus(request.text ? "Embedding your question on Bedrock, then searching…" : "Searching…");
  try {
    const result = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({ ...request, arms }),
    });
    $("question-input").value = result.question.body;
    history.replaceState(null, "", `#q=${encodeURIComponent(result.question.id)}`);
    renderResult(result);
    setStatus("VS Code's active_query now points at this question too.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function renderResult(result) {
  const { question, arms } = result;
  state.answers = new Map(question.answers.map((docId, i) => [docId, LETTERS[i] || "*"]));
  $("result").hidden = false;
  $("question-text").textContent = question.body;
  $("question-meta").textContent = question.judged
    ? `FiQA test question ${question.id}, with ${question.answers.length} known `
      + `answer${question.answers.length === 1 ? "" : "s"}`
    : "Your question. FiQA has no judgments for it, so nothing is graded.";
  renderAnswerKey(question, arms);
  const columns = $("columns");
  columns.style.setProperty("--cols", String(arms.length));
  columns.replaceChildren(...arms.map(renderColumn));
}

function renderAnswerKey(question, arms) {
  const key = $("answers");
  key.replaceChildren();
  if (!question.judged) return;
  for (const [docId, letter] of state.answers) {
    const foundBy = arms.filter((arm) => arm.rows.some((row) => row.doc_id === docId)).length;
    key.append(el("span", {
      class: "answer-key",
      title: `Post ${docId}`,
      onmouseenter: () => linkDoc(docId),
      onmouseleave: () => linkDoc(null),
      onclick: () => openDoc(docId),
    }, [
      el("span", { class: `tag${foundBy ? "" : " missing"}`, text: letter }),
      el("small", { text: foundBy ? `in ${foundBy} of ${arms.length} top 10s` : "in no top 10" }),
    ]));
  }
}

function columnFacts(card) {
  const facts = [];
  if (card.ndcg10 !== null) {
    const found = card.rows.filter((row) => row.relevant).length;
    facts.push(el("div", { text: `${found} of ${card.relevant_total} answers in the top 10` }));
  }
  const timing = `${card.elapsed_ms.toLocaleString()} ms, ${card.source}`;
  facts.push(el("div", { text: timing }));
  if (card.returned < 50) {
    facts.push(el("div", { class: "short", text: `Returned ${card.returned} of 50 candidates` }));
  }
  return el("div", { class: "column-facts" }, facts);
}

function renderColumn(card) {
  const score = card.ndcg10 === null ? "–" : Math.round(card.ndcg10 * 100).toString();
  const head = el("header", { class: "column-head" }, [
    el("div", { class: "column-title" }, [
      el("h3", { text: card.label }),
      el("button", { type: "button", class: "quiet", text: "SQL", onclick: () => openSql(card) }),
    ]),
    el("div", { class: "score-line" }, [
      el("span", { class: "ndcg", text: score }),
      el("span", { class: "ndcg-label", text: "NDCG@10" }),
    ]),
    columnFacts(card),
  ]);
  const rows = card.rows.length
    ? card.rows.map((row) => renderRow(card, row))
    : [el("li", { class: "empty", text: "No posts matched." })];
  return el("section", { class: "column", "aria-label": card.label }, [
    head,
    el("ol", { class: "rows" }, rows),
  ]);
}

function rowPills(card, row) {
  const pills = [];
  if (row.keyword_rank !== null || row.vector_rank !== null) {
    pills.push(el("span", { class: "pill", text: `keyword ${row.keyword_rank ?? "–"}` }));
    pills.push(el("span", { class: "pill", text: `vector ${row.vector_rank ?? "–"}` }));
  }
  if (card.base_label && !row.from_rank) {
    pills.push(el("span", { class: "move-up", text: `not in ${card.base_label} top 50` }));
  }
  if (card.base_label && row.from_rank) {
    const moved = row.from_rank - row.rank;
    const text = moved > 0 ? `up ${moved}, was ${row.from_rank}`
      : moved < 0 ? `down ${-moved}, was ${row.from_rank}` : `stayed at ${row.rank}`;
    pills.push(el("span", { class: moved > 0 ? "move-up" : moved < 0 ? "move-down" : "pill", text }));
  }
  return pills;
}

function renderRow(card, row) {
  const letter = state.answers.get(row.doc_id);
  return el("li", {
    class: `row${row.relevant ? " is-answer" : ""}`,
    "data-doc": row.doc_id,
    tabindex: "0",
    onmouseenter: () => linkDoc(row.doc_id),
    onmouseleave: () => linkDoc(null),
    onclick: () => openDoc(row.doc_id, card, row),
    onkeydown: (event) => event.key === "Enter" && openDoc(row.doc_id, card, row),
  }, [
    el("span", { class: "rank", text: String(row.rank) }),
    el("div", { class: "row-body" }, [
      el("div", { class: "row-top" }, [
        letter && row.relevant ? el("span", { class: "tag", text: letter }) : null,
        ...rowPills(card, row),
      ]),
      el("p", { class: "preview", text: row.preview }),
    ]),
  ]);
}

function linkDoc(docId) {
  for (const node of document.querySelectorAll(".row.linked")) node.classList.remove("linked");
  if (!docId) return;
  for (const node of document.querySelectorAll(`.row[data-doc="${CSS.escape(docId)}"]`)) {
    node.classList.add("linked");
  }
}

/* Drawer */

function openDrawer(title, children) {
  $("drawer-title").textContent = title;
  $("drawer-body").replaceChildren(...children);
  $("drawer").hidden = false;
  $("drawer-close").focus();
}

function closeDrawer() {
  $("drawer").hidden = true;
}

function rrfArithmetic(row) {
  const part = (rank) => (rank ? 1 / (RRF_K + rank) : 0);
  const terms = [];
  if (row.keyword_rank) terms.push(`1/(${RRF_K}+${row.keyword_rank})`);
  if (row.vector_rank) terms.push(`1/(${RRF_K}+${row.vector_rank})`);
  const total = part(row.keyword_rank) + part(row.vector_rank);
  return el("p", { class: "arith", text: `${terms.join(" + ")} = ${total.toFixed(5)}` });
}

async function openDoc(docId, card = null, row = null) {
  try {
    const doc = await api(`/api/doc/${encodeURIComponent(docId)}`);
    const letter = state.answers.get(docId);
    const children = [];
    if (letter) children.push(el("p", { text: `Known answer ${letter} for this question.` }));
    if (row && (row.keyword_rank || row.vector_rank) && card.stage.startsWith("rrf")) {
      children.push(el("p", { text: "Its RRF score, from its rank in each list:" }), rrfArithmetic(row));
    }
    children.push(el("p", { class: "doc-text", text: doc.body || "(This post is empty.)" }));
    openDrawer(`Post ${docId}`, children);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function openSql(card) {
  try {
    const source = await api(`/api/sql/${encodeURIComponent(card.stage)}`);
    const [explore, executed] = source.text.split(source.marker);
    const code = el("pre", { class: "sql" }, executed === undefined
      ? [el("span", { text: source.text })]
      : [
          el("span", { class: "explore", text: explore }),
          el("span", { class: "marker", text: source.marker }),
          el("span", { text: executed }),
        ]);
    const intro = el("p", {
      text: "Dimmed statements are for exploring in VS Code. The section after the marker "
        + "is what this column ran, character for character.",
    });
    openDrawer(source.file, [source.note ? el("p", { text: source.note }) : null, intro, code]
      .filter(Boolean));
  } catch (error) {
    setStatus(error.message, true);
  }
}

/* Scoreboard */

function boardRow(row, best, armsByStage) {
  const arm = armsByStage.get(row.stage);
  const classes = ["board-row", arm && arm.pitfall && "pitfall", row.stage === best && "best"];
  const track = el("div", { class: "bar-track", title: `Recall@50 ${row.recall_at_50}` }, [
    el("div", { class: "bar", style: `width:${Number(row.ndcg_at_10)}%` }),
    el("span", {
      class: Number(row.ndcg_at_10) < 12 ? "bar-value outside" : "bar-value",
      style: Number(row.ndcg_at_10) < 12
        ? `left:calc(${Math.max(Number(row.ndcg_at_10), Number(row.recall_at_50))}% + 0.6rem)`
        : null,
      text: String(row.ndcg_at_10),
    }),
    el("div", { class: "recall-mark", style: `left:${Number(row.recall_at_50)}%` }),
  ]);
  return el("div", { class: classes.filter(Boolean).join(" ") }, [
    el("span", { class: "name", text: row.label }),
    track,
    el("span", { class: "num", text: String(row.recall_at_50) }),
    el("span", { class: "num extra", text: row.p50_ms === null ? "–" : String(row.p50_ms) }),
    el("span", { class: "num extra",
      text: row.stage === "vector" ? "baseline"
        : `${row.better_than_vector} / ${row.worse_than_vector}` }),
  ]);
}

function renderSwings(listId, swings) {
  const list = $(listId);
  list.replaceChildren(...swings.map((swing) => el("li", {}, [
    el("button", {
      type: "button", text: swing.body,
      onclick: () => { showView("search"); search({ question_id: swing.id }); },
    }),
    el("small", {
      text: `RRF · BM25 ${Math.round(swing.hybrid * 100)}, vector ${Math.round(swing.vector * 100)}`,
    }),
  ])));
}

async function loadScoreboard() {
  const board = $("board");
  try {
    const data = await api("/api/scoreboard");
    const armsByStage = new Map(state.arms.map((arm) => [arm.stage, arm]));
    const best = data.rows.find((row) => !armsByStage.get(row.stage)?.pitfall)?.stage;
    const header = el("div", { class: "board-row header" }, [
      el("span", { text: "Arm" }),
      el("span", { text: "NDCG@10 (bar) and Recall@50 (line)" }),
      el("span", { class: "num", text: "Recall@50" }),
      el("span", { class: "num extra", text: "p50 ms" }),
      el("span", { class: "num extra", text: "Beat / lost to vector" }),
    ]);
    board.replaceChildren(header, ...data.rows.map((row) => boardRow(row, best, armsByStage)));
    renderSwings("swings-gain", data.swings.filter((s) => s.direction === "gain"));
    renderSwings("swings-loss", data.swings.filter((s) => s.direction === "loss"));
  } catch (error) {
    board.replaceChildren(el("p", { class: "status error", text: error.message }));
  }
}

/* Views and startup */

function showView(view) {
  for (const tab of document.querySelectorAll(".tab")) {
    if (tab.dataset.view === view) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  $("view-search").hidden = view !== "search";
  $("view-scoreboard").hidden = view !== "scoreboard";
  if (view === "scoreboard") loadScoreboard();
}

function bindEvents() {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => showView(tab.dataset.view));
  }
  $("ask").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = $("question-input").value.trim();
    const questionId = state.matches.get(text);
    search(questionId ? { question_id: questionId } : { text });
  });
  let timer;
  $("question-input").addEventListener("input", (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => loadQuestions(event.target.value).catch(() => {}), 200);
  });
  $("drawer-close").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawer();
    const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName);
    if (event.key === "/" && !typing) {
      event.preventDefault();
      $("question-input").focus();
    }
  });
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    const ext = status.extensions;
    const parts = [`PostgreSQL ${status.postgres.split(" ")[0]}`, `pgvector ${ext.vector}`];
    if (ext.pg_textsearch) parts.push(`pg_textsearch ${ext.pg_textsearch}`);
    parts.push(`${status.embedded.toLocaleString()} of ${status.docs.toLocaleString()} posts embedded`);
    $("versions").textContent = parts.join(", ");
  } catch (error) {
    $("versions").textContent = error.message;
  }
}

async function start() {
  bindEvents();
  await Promise.all([loadStatus(), loadArms()]);
  const data = await loadQuestions();
  renderDemoQuestions(data.demo);
  const match = location.hash.match(/^#q=(.+)$/);
  if (match) search({ question_id: decodeURIComponent(match[1]) });
}

start().catch((error) => setStatus(error.message, true));
