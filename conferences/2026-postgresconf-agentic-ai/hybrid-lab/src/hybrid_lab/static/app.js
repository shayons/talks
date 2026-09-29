const RRF_K = 60;
const STORE_KEY = "hybrid-lab-arms";
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const INLINE_ANSWERS = 6;
let drawerReturnFocus = null;
let searchVersion = 0;
let datasetVersion = 0;

const state = {
  dataset: null, datasets: [], arms: [], selected: new Set(), matches: new Map(),
  answers: new Map(), demos: new Map(),
};
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

function withDataset(path) {
  if (!state.dataset) return path;
  return `${path}${path.includes("?") ? "&" : "?"}dataset=${encodeURIComponent(state.dataset)}`;
}

async function api(path, options = {}) {
  const response = await fetch(options.method ? path : withDataset(path), {
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
    const saved = JSON.parse(localStorage.getItem(`${STORE_KEY}:${state.dataset}`) || "null");
    return Array.isArray(saved) ? saved : null;
  } catch {
    return null;
  }
}

function saveSelection() {
  try {
    localStorage.setItem(`${STORE_KEY}:${state.dataset}`, JSON.stringify([...state.selected]));
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
      renderBlendHelp();
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
  renderBlendHelp();
}

function blendFormula(blend) {
  const vector = Math.round(blend.vector_weight * 100);
  return `${vector}% vector + ${100 - vector}% ${blend.keyword}`;
}

function renderBlendHelp() {
  const help = $("blend-help");
  const blends = state.arms.filter((arm) => arm.blend && state.selected.has(arm.stage));
  help.hidden = !blends.length && !document.querySelector(".arm-more").open;
  help.replaceChildren();
  if (help.hidden) return;
  help.append(el("p", {}, [
    el("strong", { text: "Tuned blend" }),
    " = a weighted mix of keyword and vector scores, each scaled to 0–1 within its result list. "
      + "We choose the weight with the best NDCG@10 on separate development questions, "
      + "then keep it fixed for test questions.",
  ]));
  for (const arm of blends) {
    help.append(el("p", { class: "blend-weight" }, [
      el("strong", { text: `${arm.label}: ${blendFormula(arm.blend)}.` }),
      arm.blend.tuned ? " Fixed for this corpus, not adjusted for this sample."
        : state.dataset === "scidocs"
          ? " SCIDOCS has no development questions, so this weight is not tuned."
          : " This uses the fixed 50/50 default; no weight has been tuned.",
    ]));
  }
}

async function loadArms(version = datasetVersion) {
  const arms = await api("/api/arms");
  if (version !== datasetVersion) return;
  state.arms = arms;
  const saved = savedSelection();
  const defaults = state.arms.filter((arm) => arm.default_on).map((arm) => arm.stage);
  const available = new Set(state.arms.filter((arm) => arm.available).map((arm) => arm.stage));
  state.selected = new Set((saved || defaults).filter((stage) => available.has(stage)));
  renderArms();
}

/* Questions */

async function loadQuestions(term = "", version = datasetVersion) {
  const data = await api(`/api/questions?q=${encodeURIComponent(term)}`);
  if (version !== datasetVersion) return null;
  const list = $("question-matches");
  list.replaceChildren();
  for (const match of data.matches) {
    state.matches.set(match.body, match.id);
    list.append(el("option", { value: match.body }));
  }
  return data;
}

function renderDemoQuestions(demo) {
  state.demos = new Map(demo.map((item) => [item.id, item]));
  const picks = $("demo-questions");
  picks.replaceChildren();
  for (const item of demo) {
    state.matches.set(item.body, item.id);
    picks.append(el("button", {
      type: "button", class: "pick", title: item.reason, "data-id": item.id,
      onclick: () => search({ question_id: item.id }),
    }, [el("strong", { text: item.label }), el("span", { text: item.body })]));
  }
}

/* Search */

async function search(request) {
  const arms = state.arms.map((arm) => arm.stage).filter((stage) => state.selected.has(stage));
  if (!arms.length) {
    setStatus("Choose at least one search method.", true);
    return;
  }
  const version = ++searchVersion;
  const dataset = state.dataset;
  const button = document.querySelector("#ask .primary");
  button.disabled = true;
  $("example-insight").hidden = true;
  setStatus(request.text ? "Embedding your question on Bedrock, then searching…" : "Searching…");
  try {
    const result = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({ ...request, arms, dataset }),
    });
    if (version !== searchVersion || dataset !== state.dataset) return;
    $("question-input").value = result.question.body;
    const hash = `#d=${encodeURIComponent(state.dataset)}&q=${encodeURIComponent(result.question.id)}`;
    history.replaceState(null, "", hash);
    renderResult(result);
    setStatus("");
  } catch (error) {
    if (version === searchVersion) setStatus(error.message, true);
  } finally {
    if (version === searchVersion) button.disabled = false;
  }
}

function renderResult(result) {
  const { question, arms } = result;
  const visibleAnswers = new Set(arms.flatMap((arm) => arm.rows
    .filter((row) => row.relevant).map((row) => row.doc_id)));
  // Keep the short legends stable; on broad questions, label visible answers first.
  const orderedAnswers = question.answers.length > INLINE_ANSWERS
    ? [...question.answers.filter((id) => visibleAnswers.has(id)),
       ...question.answers.filter((id) => !visibleAnswers.has(id))]
    : question.answers;
  state.answers = new Map(orderedAnswers.map((docId, i) => [docId, answerLabel(i)]));
  $("result").hidden = false;
  $("question-text").textContent = question.body;
  const context = {
    scifact: "Find evidence for this claim. A known answer may support or refute it.",
    scidocs: "Find papers cited by this title. The blend uses a fixed 50/50 weight; this corpus has no tuning split.",
  }[state.dataset];
  $("question-context").textContent = context || "";
  $("question-context").hidden = !context;
  const set = datasetLabel();
  $("question-meta").textContent = question.judged
    ? `${set} test question ${question.id}, with ${question.answers.length} known `
      + `answer${question.answers.length === 1 ? "" : "s"}, also active in VS Code`
    : `Your question. ${set} has no judgments for it, so nothing is graded.`;
  renderAnswerKey(question, arms);
  for (const pick of document.querySelectorAll(".pick")) {
    pick.classList.toggle("current", pick.dataset.id === question.id);
  }
  const leader = leadingStage(arms);
  const columns = $("columns");
  columns.style.setProperty("--cols", String(arms.length));
  columns.replaceChildren(...arms.map((card) => renderColumn(card, card.stage === leader)));
  renderExampleInsight(question, arms);
}

function renderExampleInsight(question, arms) {
  const panel = $("example-insight");
  const example = question.judged && state.demos.get(question.id);
  panel.replaceChildren();
  panel.hidden = !example?.reason;
  if (panel.hidden) return;
  const defaults = state.arms.filter((arm) => arm.default_on && arm.available);
  const showingDefaults = defaults.length === arms.length
    && defaults.every((arm) => arms.some((card) => card.stage === arm.stage));
  panel.append(
    el("h3", { id: "example-insight-title", text: "Why this result" }),
    el("div", { class: "example-insight-body" }, [
      el("p", { text: example.reason }),
      el("div", { class: "example-insight-footer" }, [
        el("span", { text: showingDefaults
          ? "One question. Compare the full test set on the Scoreboard."
          : "This explanation compares the example’s default methods." }),
        showingDefaults
          ? el("button", { type: "button", class: "insight-action", text: "See overall results",
              onclick: () => showView("scoreboard") })
          : el("button", { type: "button", class: "insight-action", text: "Show example methods",
              onclick: () => {
                state.selected = new Set(defaults.map((arm) => arm.stage));
                saveSelection();
                renderArms();
                search({ question_id: question.id });
              } }),
      ]),
    ]),
  );
}

function leadingStage(arms) {
  const graded = arms.filter((card) => card.ndcg10 !== null);
  if (graded.length < 2) return null;
  const best = Math.max(...graded.map((card) => card.ndcg10));
  const leaders = graded.filter((card) => card.ndcg10 === best);
  return leaders.length === 1 ? leaders[0].stage : null;
}

function answerLabel(index) {
  let label = "";
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / LETTERS.length)) {
    label = LETTERS[(n - 1) % LETTERS.length] + label;
  }
  return label;
}

function answerButton(docId, letter, foundBy, total, compact = false) {
  const coverage = foundBy ? `in ${foundBy} of ${total} top 10s` : "in no top 10";
  return el("button", {
    type: "button", class: "answer-key",
    title: `Known answer ${letter}: ${coverage}. Document ${docId}`,
    "aria-label": `Known answer ${letter}, ${coverage}. Open document ${docId}`,
    onmouseenter: () => linkDoc(docId),
    onmouseleave: () => linkDoc(null),
    onfocus: () => linkDoc(docId),
    onblur: () => linkDoc(null),
    onclick: () => openDoc(docId),
  }, [
    el("span", { class: `tag${foundBy ? "" : " missing"}`, text: letter }),
    compact ? null : el("small", { text: coverage }),
  ]);
}

function renderAnswerKey(question, arms) {
  const key = $("answers");
  key.replaceChildren();
  if (!question.judged) return;
  const answers = [...state.answers].map(([docId, letter]) => ({
    docId, letter,
    foundBy: arms.filter((arm) => arm.rows.some((row) => row.doc_id === docId)).length,
  }));
  if (answers.length <= INLINE_ANSWERS) {
    key.append(...answers.map(({ docId, letter, foundBy }) =>
      answerButton(docId, letter, foundBy, arms.length)));
    return;
  }
  const shown = answers.filter((answer) => answer.foundBy);
  key.append(
    el("p", { class: "answer-summary" }, [
      el("strong", { text: `${shown.length} of ${answers.length} known answers` }),
      " appear across these top 10s.",
    ]),
    el("div", { class: "answer-overview" }, [
      el("div", { class: "answer-tags" }, shown.slice(0, 10).map(({ docId, letter, foundBy }) =>
        answerButton(docId, letter, foundBy, arms.length, true))),
      shown.length ? el("span", { class: "note", text: "Same letter, same answer." }) : null,
      el("button", {
        type: "button", class: "answer-browse", text: `Browse all ${answers.length} answers`,
        onclick: () => openAnswerList(answers, arms.length),
      }),
    ]),
  );
}

function openAnswerList(answers, total) {
  const shown = answers.filter((answer) => answer.foundBy);
  const missing = answers.filter((answer) => !answer.foundBy);
  const children = [el("p", { class: "note", text:
    "Green marks a known answer. Match its letter across columns, or select it to read the document." })];
  for (const [title, group] of [["In these top 10s", shown], ["Outside these top 10s", missing]]) {
    if (!group.length) continue;
    children.push(el("h3", { text: `${title} (${group.length})` }),
      el("ul", { class: "answer-list" }, group.map(({ docId, letter, foundBy }) =>
        el("li", {}, [answerButton(docId, letter, foundBy, total),
          el("span", { class: "note", text: docId })]))));
  }
  openDrawer(`${answers.length} known answers`, children);
}

function columnFacts(card) {
  const facts = [];
  const blend = state.arms.find((arm) => arm.stage === card.stage)?.blend;
  if (blend) facts.push(el("div", { class: "blend-formula", text: blendFormula(blend) }));
  if (card.ndcg10 !== null) {
    const found = card.rows.filter((row) => row.relevant).length;
    const noun = card.relevant_total === 1 ? "answer" : "answers";
    facts.push(el("div", { text: `${found} of ${card.relevant_total} ${noun} in the top 10` }));
  }
  const timing = `${card.elapsed_ms.toLocaleString()} ms, ${card.source}`;
  facts.push(el("div", { text: timing }));
  if (card.returned < 50) {
    facts.push(el("div", { class: "short", text: `Returned ${card.returned} of 50 results` }));
  }
  return el("div", { class: "column-facts" }, facts);
}

function renderColumn(card, leads) {
  const score = card.ndcg10 === null ? "–" : Math.round(card.ndcg10 * 100).toString();
  const head = el("header", { class: "column-head" }, [
    el("div", { class: "column-title" }, [
      el("h3", { text: card.label }),
      el("button", { type: "button", class: "quiet", text: "SQL", onclick: () => openSql(card) }),
    ]),
    el("div", { class: "score-line" }, [
      el("span", { class: "ndcg", text: score }),
      el("span", { class: "ndcg-label", text: "NDCG@10" }),
      leads ? el("span", { class: "leader-chip", text: "Highest" }) : null,
    ]),
    columnFacts(card),
  ]);
  const rows = card.rows.length
    ? card.rows.map((row) => renderRow(card, row))
    : [el("li", { class: "empty", text: "No documents matched." })];
  return el("section", { class: `column${leads ? " leader" : ""}`, "aria-label": card.label }, [
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
  if ($("drawer").hidden) drawerReturnFocus = document.activeElement;
  $("drawer-title").textContent = title;
  $("drawer-body").replaceChildren(...children);
  $("drawer").hidden = false;
  $("drawer-close").focus();
}

function closeDrawer() {
  $("drawer").hidden = true;
  drawerReturnFocus?.focus();
  drawerReturnFocus = null;
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
    children.push(el("p", { class: "doc-text", text: doc.body || "(This document is empty.)" }));
    openDrawer(`Document ${docId}`, children);
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
  const blend = state.arms.find((arm) => arm.stage === "blend_local");
  const label = blend?.blend?.tuned ? "Tuned blend" : "Untuned 50/50 blend";
  list.replaceChildren(...swings.map((swing) => el("li", {}, [
    el("button", {
      type: "button", text: swing.body,
      onclick: () => { showView("search"); search({ question_id: swing.id }); },
    }),
    el("small", {
      text: `${label} ${Math.round(swing.hybrid * 100)}, bge-small alone ${Math.round(swing.vector * 100)}`,
    }),
  ])));
}

function datasetLabel() {
  const found = state.datasets.find((d) => d.name === state.dataset);
  return found ? found.label.split(" (")[0] : "This dataset";
}

function summaryTable(data) {
  const header = el("tr", {}, [
    el("th", { text: "Method" }),
    ...data.datasets.map((d) => el("th", {}, [
      d.label.split(" (")[0],
      el("small", { text: d.blend_weight === null ? "50/50, untuned" : "Tuned per model" }),
    ])),
  ]);
  const best = Object.fromEntries(data.datasets.map((d) => [d.name, Math.max(
    ...data.arms.map((arm) => arm.cells[d.name] ?? -1))]));
  const rows = data.arms.map((arm) => el("tr", {}, [
    el("td", { text: arm.label.replace("Tuned blend", "Blend") }),
    ...data.datasets.map((d) => {
      const value = arm.cells[d.name];
      return el("td", {
        class: value !== undefined && value === best[d.name] ? "best" : null,
        text: value === undefined ? "–" : value.toFixed(1),
      });
    }),
  ]));
  return el("table", {}, [el("thead", {}, header), el("tbody", {}, rows)]);
}

async function loadSummary() {
  try {
    const data = await api("/api/summary");
    $("summary-section").hidden = data.datasets.length < 2;
    $("summary").replaceChildren(summaryTable(data));
  } catch (error) {
    $("summary").replaceChildren(el("p", { class: "status error", text: error.message }));
  }
}

async function loadScoreboard() {
  const board = $("board");
  $("board-title").textContent = `How each method did on ${datasetLabel()}`;
  loadSummary();
  try {
    const data = await api("/api/scoreboard");
    const armsByStage = new Map(state.arms.map((arm) => [arm.stage, arm]));
    const best = data.rows.find((row) => !armsByStage.get(row.stage)?.pitfall)?.stage;
    const header = el("div", { class: "board-row header" }, [
      el("span", { text: "Method" }),
      el("span", { text: "NDCG@10 (bar) and Recall@50 (line)" }),
      el("span", { class: "num", text: "Recall@50" }),
      el("span", { class: "num extra", text: "Median ms" }),
      el("span", { class: "num extra", text: "Better / worse than Embed v4" }),
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
  $("reset-demo").addEventListener("click", resetDemo);
  document.querySelector(".arm-more").addEventListener("toggle", renderBlendHelp);
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

function embeddingCoverage({ docs, embedded, empty }) {
  const withText = docs - empty;
  if (embedded < withText) {
    return `${embedded.toLocaleString()} of ${withText.toLocaleString()} documents embedded`;
  }
  const skipped = empty ? ` (${empty.toLocaleString()} empty in the source)` : "";
  return `All ${embedded.toLocaleString()} documents embedded${skipped}`;
}

async function loadStatus(version = datasetVersion) {
  try {
    const status = await api("/api/status");
    if (version !== datasetVersion) return;
    const ext = status.extensions;
    const parts = [`PostgreSQL ${status.postgres.split(" ")[0]}`, `pgvector ${ext.vector}`];
    if (ext.pg_textsearch) parts.push(`pg_textsearch ${ext.pg_textsearch}`);
    $("versions").replaceChildren(
      el("span", { text: parts.join(", ") }),
      el("span", { text: embeddingCoverage(status) }),
    );
  } catch (error) {
    if (version === datasetVersion) $("versions").textContent = error.message;
  }
}

async function loadDataset() {
  const version = ++datasetVersion;
  ++searchVersion;
  document.querySelector("#ask .primary").disabled = false;
  state.matches = new Map();
  state.demos = new Map();
  $("result").hidden = true;
  setStatus("");
  await Promise.all([loadStatus(version), loadArms(version)]);
  if (version !== datasetVersion) return;
  const data = await loadQuestions("", version);
  if (!data || version !== datasetVersion) return;
  renderDemoQuestions(data.demo);
  if (!$("view-scoreboard").hidden) loadScoreboard();
}

async function resetDemo() {
  const button = $("reset-demo");
  button.disabled = true;
  try {
    ++searchVersion;
    closeDrawer();
    showView("search");
    for (const details of document.querySelectorAll(".arm-more")) details.open = false;
    for (const dataset of state.datasets) {
      try { localStorage.removeItem(`${STORE_KEY}:${dataset.name}`); } catch { /* Private window. */ }
    }
    state.dataset = state.datasets.find((dataset) => dataset.name === "fiqa")?.name
      || state.datasets[0].name;
    $("dataset").value = state.dataset;
    $("question-input").value = "";
    history.replaceState(null, "", `#d=${encodeURIComponent(state.dataset)}`);
    const version = datasetVersion + 1;
    await loadDataset();
    if (version !== datasetVersion) return;
    // Restore in memory too, even if this browser refuses localStorage changes.
    state.selected = new Set(state.arms.filter((arm) => arm.default_on && arm.available)
      .map((arm) => arm.stage));
    saveSelection();
    renderArms();
    const first = state.demos.keys().next().value;
    if (first) await search({ question_id: first });
    else setStatus("No stage questions are configured for this dataset.", true);
    window.scrollTo({ top: 0, behavior: "instant" });
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function loadDatasets() {
  state.datasets = await api("/api/datasets");
  const params = new URLSearchParams(location.hash.slice(1));
  const wanted = params.get("d");
  state.dataset = state.datasets.some((d) => d.name === wanted) ? wanted : state.datasets[0].name;
  const select = $("dataset");
  select.replaceChildren(...state.datasets.map((d) => el("option", {
    value: d.name,
    text: `${d.label}, ${d.questions} test questions`,
  })));
  select.value = state.dataset;
  select.addEventListener("change", () => {
    state.dataset = select.value;
    history.replaceState(null, "", `#d=${encodeURIComponent(state.dataset)}`);
    loadDataset().catch((error) => setStatus(error.message, true));
  });
  return params.get("q");
}

async function followHash() {
  const hash = location.hash;
  const params = new URLSearchParams(hash.slice(1));
  const question = params.get("q");
  if (question) {
    closeDrawer();
    showView("search");
  }
  const wanted = params.get("d");
  if (wanted && wanted !== state.dataset && state.datasets.some((d) => d.name === wanted)) {
    state.dataset = wanted;
    $("dataset").value = wanted;
    await loadDataset();
  }
  if (question && hash === location.hash) await search({ question_id: question });
}

async function start() {
  bindEvents();
  const question = await loadDatasets();
  await loadDataset();
  if (question) search({ question_id: question });
  window.addEventListener("hashchange", () => {
    followHash().catch((error) => setStatus(error.message, true));
  });
}

start().catch((error) => setStatus(error.message, true));
