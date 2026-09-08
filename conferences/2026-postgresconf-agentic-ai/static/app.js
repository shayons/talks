import { consumeEvents } from "./stream.mjs";
import { safeMarkup } from "./render.mjs";

const $ = (s) => document.querySelector(s);
const el = (t, c, h) => {
  const e = document.createElement(t);
  if (c) e.className = c;
  if (h !== undefined) e.innerHTML = h;
  return e;
};
const esc = (s) =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

const REGULARS = {
  u_marco: {
    name: "Marco",
    title: "Pour-over regular",
    ask: "Fruity East African, medium roast.",
    lesson: "Three kinds of memory in one plan.",
    cls: "marco",
    portrait: "/static/portraits/marco.jpg",
    prompts: [
      { q: "Cold brew options", label: "Cold brew options" },
      { q: "Something lighter and more floral", label: "Lighter and more floral" },
    ],
  },
  u_ana: {
    name: "Ana",
    title: "Espresso, by the kilo",
    ask: "Dark, chocolatey, low-acid.",
    lesson: "Memory continuity + approvals.",
    cls: "ana",
    portrait: "/static/portraits/ana.jpg",
    prompts: [
      { q: "Cold brew options", label: "Cold brew options" },
      { q: "order that", label: "Order that" },
    ],
  },
  u_yuki: {
    name: "Yuki",
    title: "Tokyo specialty buyer",
    ask: "Japanese single-origins, siphon.",
    lesson: "Catalog miss + MCP.",
    cls: "yuki",
    portrait: "/static/portraits/yuki.jpg",
    prompts: [
      { q: "Any Japanese single-origins in stock?", label: "Japanese single-origins" },
      { q: "What do you have from Asia-Pacific then?", label: "Asia-Pacific instead" },
    ],
  },
};

const FALLBACK_PROMPTS = [
  { q: "Cold brew options", label: "Cold brew options" },
  { q: "Smooth espresso", label: "Smooth espresso" },
  { q: "Light roast pour-over", label: "Light roast" },
  { q: "Order a bag of cold brew", label: "Place an order" },
];

function kwify(sql) {
  let s = esc(sql);
  s = s.replace(/--[^\n]*/g, (m) => `\u0001${m}\u0002`);
  s = s.replace(/'[^']*'/g, (m) => `\u0003${m}\u0004`);
  s = s.replace(/\$\d+/g, (m) => `\u0003${m}\u0004`);
  s = s.replace(
    /\b(SELECT|FROM|WHERE|AND|OR|ORDER BY|LIMIT|JOIN|LEFT|INNER|ON|AS|GROUP BY|DESC|ASC|INSERT|INTO|VALUES|UPDATE|SET|RETURNING|WITH|BEGIN|COMMIT|CREATE|TABLE|INDEX|USING|EXTENSION|PRIMARY|KEY|NOT|NULL|DEFAULT|TRUE|FALSE|ANY|IN)\b/g,
    "\u0005$1\u0006",
  );
  s = s.replace(/(&lt;=&gt;|&lt;-&gt;|&lt;#&gt;)/g, "\u0007$1\u0008");
  s = s.replace(/\u0001/g, '<span class="cmt">').replace(/\u0002/g, "</span>");
  s = s.replace(/\u0003/g, '<span class="str">').replace(/\u0004/g, "</span>");
  s = s.replace(/\u0005/g, '<span class="kw">').replace(/\u0006/g, "</span>");
  s = s.replace(/\u0007/g, '<span class="op">').replace(/\u0008/g, "</span>");
  return s;
}

const state = {
  customers: [],
  customerId: null,
  sessionId: null,
  busy: false,
  ready: false,
  routes: [],
  startedAt: 0,
  timer: null,
};

function renderRegulars() {
  const host = $("#regulars");
  host.innerHTML = "";
  const ids = state.customers.map((c) => c.id);
  const shown = ids.filter((id) => REGULARS[id]);
  const list = shown.length ? shown : ids.slice(0, 3);
  list.forEach((id) => {
    const c = state.customers.find((x) => x.id === id);
    const meta = REGULARS[id] || {
      name: c?.name || id,
      title: c?.summary || "Customer",
      ask: "",
      lesson: "",
      cls: "other",
    };
    const face = meta.portrait
      ? `<img src="${meta.portrait}" alt="">`
      : `<span class="mono ${meta.cls}">${esc(c.name.charAt(0))}</span>`;
    const b = el("button", "regular");
    b.type = "button";
    b.setAttribute("aria-pressed", id === state.customerId ? "true" : "false");
    b.innerHTML = `
      ${face}
      <span class="who">
        <div class="name">${esc(c.name)}</div>
        <div class="title">${esc(meta.title)}</div>
        ${meta.ask ? `<div class="ask">“${esc(meta.ask)}”</div>` : ""}
        ${meta.lesson ? `<div class="lesson">${esc(meta.lesson)}</div>` : ""}
      </span>`;
    b.addEventListener("click", () => {
      if (state.busy) return;
      $("#customer").value = id;
      state.customerId = id;
      onCustomerChange();
    });
    host.appendChild(b);
  });
}

function renderPills() {
  const host = $("#pills");
  host.innerHTML = "";
  const prompts = (REGULARS[state.customerId] || {}).prompts || FALLBACK_PROMPTS;
  prompts.forEach((p) => {
    const b = el("button", "pill", esc(p.label));
    b.dataset.q = p.q;
    b.addEventListener("click", () => run(p.q));
    host.appendChild(b);
  });
}

async function getJSON(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`Connection failed (${response.status}).`);
  return response.json();
}

function syncControls() {
  document.querySelectorAll(".regular, .new-session, .pill, #customer, #modelRoute, #q, #send")
    .forEach((control) => { control.disabled = state.busy || !state.ready; });
  $("#chat").setAttribute("aria-busy", String(state.busy));
}

function modelDetail() {
  const route = state.routes.find((r) => r.id === $("#modelRoute").value);
  $("#modelDetail").textContent = route
    ? `${route.intent_model} → ${route.response_model}` : "No model route configured.";
}

async function init() {
  state.ready = false;
  syncControls();
  $("#retry").hidden = true;
  $("#connection").textContent = "Connecting to the roastery…";
  try {
    const [customers, config] = await Promise.all([
      getJSON("/api/customers"), getJSON("/api/chat/config"),
    ]);
    if (!Array.isArray(customers) || !customers.length)
      throw new Error("No customers found. Initialize the demo database, then retry.");
    state.customers = customers;
    const sel = $("#customer");
    sel.replaceChildren(...customers.map((c) => new Option(c.name, c.id)));
    state.routes = config.routes || [];
    const model = $("#modelRoute");
    model.replaceChildren(...state.routes.map((r) => {
      const option = new Option(r.label + (r.configured ? "" : " · needs API key"), r.id);
      option.disabled = !r.configured;
      return option;
    }));
    const selected = state.routes.find((r) => r.id === config.default && r.configured)
      || state.routes.find((r) => r.configured);
    if (!selected) throw new Error("Configure a model route on the server, then retry.");
    model.value = selected.id;
    modelDetail();
    state.customerId = customers[0].id;
    state.ready = true;
    onCustomerChange();
    $("#connection").textContent = "PostgreSQL connected";
  } catch (error) {
    $("#connection").textContent = error.message + " Check the server and database.";
    $("#retry").hidden = false;
  } finally {
    syncControls();
  }
}

$("#customer").addEventListener("change", () => {
  if (state.busy) return;
  state.customerId = $("#customer").value;
  onCustomerChange();
});
$("#modelRoute").addEventListener("change", modelDetail);
$("#retry").addEventListener("click", init);
$("#reset").addEventListener("click", resetSession);
$("#send").addEventListener("click", () => run($("#q").value));
$("#q").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.isComposing) {
    e.preventDefault();
    run($("#q").value);
  }
});
document.querySelectorAll(".side-tab").forEach((t) => {
  t.addEventListener("click", () => switchTab(t.dataset.tab));
});
window.addEventListener("keydown", (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey || e.target.isContentEditable) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
  if (e.key === "1") selectByIndex(0);
  if (e.key === "2") selectByIndex(1);
  if (e.key === "3") selectByIndex(2);
  if (e.key === "/") { e.preventDefault(); $("#q").focus(); }
});
function showCitation(e) {
  const cite = e.target.closest("cite[data-k]");
  if (!cite) return;
  const pop = $("#citePop");
  pop.textContent = `Postgres row · ${cite.dataset.k}`;
  pop.classList.add("on");
  const rect = cite.getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(window.innerWidth - pop.offsetWidth - 8, rect.left)) + "px";
  pop.style.top = Math.min(window.innerHeight - pop.offsetHeight - 8, rect.bottom + 6) + "px";
}
for (const event of ["mouseover", "focusin"]) document.addEventListener(event, showCitation);
for (const event of ["mouseout", "focusout"]) document.addEventListener(event, (e) => {
  if (e.target.closest("cite[data-k]")) $("#citePop").classList.remove("on");
});

function selectByIndex(i) {
  if (state.busy || !state.ready) return;
  const c = state.customers[i];
  if (!c) return;
  $("#customer").value = c.id;
  state.customerId = c.id;
  onCustomerChange();
}

function onCustomerChange() {
  if (state.busy) return;
  $("#q").value = "";
  $("#citePop").classList.remove("on");
  const c = state.customers.find((x) => x.id === state.customerId);
  const chat = $("#chat");
  chat.innerHTML = "";
  const m = el("div", "msg agent");
  const firstName = c ? c.name.split(" ")[0] : "there";
  m.innerHTML = `<span class="label">Coordinator</span>
    Hey there. I coordinate our roasting and flavor teams to find you the right beans. What kind of coffee are you after, ${esc(firstName)}?`;
  chat.appendChild(m);
  $("#avatar").textContent = firstName.charAt(0).toUpperCase();
  state.sessionId = null;
  const sid = $("#sid");
  if (sid) sid.textContent = "—";
  emptyTelemetry();
  setTeleCount(0);
  renderRegulars();
  renderPills();
  syncControls();
}

function emptyTelemetry() {
  $("#panels").innerHTML = `
    <div class="empty">
<div class="title">No live events yet</div>
<div class="hint">Ask something to see the agents work</div>
    </div>`;
}

function setTeleCount(n) {
  const node = $("#teleCount");
  if (node) node.textContent = String(n);
}

function switchTab(name) {
  document
    .querySelectorAll(".side-tab")
    .forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
  $("#archView").style.display = name === "arch" ? "" : "none";
  $("#teleView").style.display = name === "tele" ? "" : "none";
  $("#sideTitleText").textContent =
    name === "arch" ? "System architecture" : "Agent telemetry";
  $("#sideSubText").textContent =
    name === "arch"
      ? "Multi-agent orchestration on Postgres"
      : "Live trace of agent activity";
}

function resetSession() {
  if (state.busy) return;
  state.sessionId = null;
  const sid = $("#sid");
  if (sid) sid.textContent = "—";
  const node = $("#elapsed");
  if (node) node.textContent = "0ms";
  onCustomerChange();
  switchTab("arch");
}

let currentPlan = null;

function followChat(wasAtBottom) {
  if (wasAtBottom) $("#chat").scrollTop = $("#chat").scrollHeight;
}

async function run(query) {
  query = query.trim();
  if (state.busy || !state.ready || !query || query.length > 2000) return;
  state.busy = true;
  syncControls();
  const chat = $("#chat");
  chat.appendChild(el("div", "msg user", esc(query)));
  $("#q").value = "";
  const think = el("div", "thinking", "Reading the catalog…");
  chat.appendChild(think);
  followChat(true);
  $("#announcement").textContent = "Finding coffee. The reply will appear as it arrives.";
  $("#panels").replaceChildren();
  currentPlan = null;
  let count = 0;
  let message = null;
  let text = "";
  let finalResponse = null;
  let done = false;
  setTeleCount(0);
  switchTab("tele");
  state.startedAt = performance.now();
  state.timer = setInterval(() => {
    $("#elapsed").textContent = Math.round(performance.now() - state.startedAt) + "ms";
  }, 100);
  function reply() {
    if (!message) {
      think.remove();
      message = el("div", "msg agent");
      message.innerHTML = '<span class="label">Coordinator · writing reply</span><div class="body"></div>';
      chat.appendChild(message);
    }
    return message;
  }
  try {
    const response = await fetch("/api/query/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
      signal: AbortSignal.timeout(190000),
      body: JSON.stringify({ customer_id: state.customerId, query,
        session_id: state.sessionId, model_route: $("#modelRoute").value }),
    });
    await consumeEvents(response, (event) => {
      const atBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 90;
      if (event.type === "session") {
        state.sessionId = event.session_id;
        $("#sid").textContent = event.session_id.slice(0, 8);
        $("#sid").title = event.session_id;
      } else if (event.type === "status") {
        think.textContent = event.message || event.text || "Reading the catalog…";
      } else if (event.type === "plan") {
        renderPlan(event);
        setTeleCount(++count);
      } else if (event.type === "step") {
        updateStep(event);
      } else if (event.type === "panel") {
        renderPanel(event);
        setTeleCount(++count);
      } else if (event.type === "text_delta") {
        text += event.text;
        reply().querySelector(".body").replaceChildren(safeMarkup(text));
      } else if (event.type === "response") {
        finalResponse = event;
        reply().querySelector(".body").replaceChildren(safeMarkup(event.text,
          new Set((event.citations || []).map((c) => c.key))));
      } else if (event.type === "done") {
        done = true;
      }
      followChat(atBottom);
    });
    if (!done || !finalResponse) throw new Error("The server did not complete the reply.");
    const atBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 90;
    finishResponse(reply(), finalResponse);
    // Keep the completed answer and first product in view when the card list
    // expands; jumping to the last card hides the recommendation just read.
    if (atBottom) chat.scrollTop = message.offsetTop - chat.offsetTop;
    $("#announcement").textContent = "Reply complete. " + reply().querySelector(".body").textContent;
  } catch (error) {
    think.remove();
    if (message) {
      message.classList.add("incomplete");
      message.querySelector(".label").textContent = "Coordinator · incomplete reply";
    }
    const notice = el("div", "msg agent error");
    notice.setAttribute("role", "alert");
    notice.textContent = `${error.name === "TimeoutError" ? "The reply timed out." : error.message} Your question is restored below. Check the trace before resending an order request.`;
    chat.appendChild(notice);
    $("#q").value = query;
    followChat(true);
    $("#announcement").textContent = "The reply could not finish. Your question has been restored.";
  } finally {
    think.remove();
    clearInterval(state.timer);
    state.busy = false;
    syncControls();
    $("#q").focus({ preventScroll: true });
  }
}

function renderPlan(ev) {
  const p = el("div", "panel");
  p.innerHTML = `
    <div class="panel-head">
<span class="tag">PLAN</span>
<span class="title">${esc(ev.title)}</span>
<span class="dur">~${esc(ev.duration_ms)}ms</span>
    </div>
    <div class="panel-body">
<div class="plan">
  <ol>
    ${ev.steps
      .map(
        (s, i) => `
      <li>
        <span class="n">${String(i + 1).padStart(2, "0")}</span>
        <span class="t">${esc(s)}</span>
        <span class="s">queued</span>
      </li>`,
      )
      .join("")}
  </ol>
</div>
    </div>`;
  $("#panels").appendChild(p);
  $("#panels").scrollTop = $("#panels").scrollHeight;
  currentPlan = p;
}

function updateStep(ev) {
  if (!currentPlan) return;
  const li = currentPlan.querySelectorAll(".plan li")[ev.index];
  if (!li) return;
  li.classList.remove("active", "done");
  if (ev.state === "active") {
    li.classList.add("active");
    li.querySelector(".s").textContent = "running";
  } else if (ev.state === "done") {
    li.classList.add("done");
    li.querySelector(".s").textContent = "ok";
  }
}

function renderPanel(ev) {
  const p = el("div", "panel");
  const tagCls =
    ["amber", "green", "purple"].includes(ev.tag_class) ? ` ${ev.tag_class}` : "";
  p.innerHTML = `
    <div class="panel-head">
<span class="tag${tagCls}">${esc(ev.tag)}</span>
<span class="title">${esc(ev.title)}</span>
<span class="dur">${ev.duration_ms ? esc(ev.duration_ms) + "ms" : ""}</span>
    </div>
    <div class="panel-body"></div>`;
  const body = p.querySelector(".panel-body");

  if (ev.sql) {
    const s = el("div", "sql");
    s.innerHTML = kwify(ev.sql);
    body.appendChild(s);
  }
  if (ev.columns && ev.columns.length) {
    const cols = ev.columns.length;
    const gridCols = `repeat(${cols}, minmax(min-content, 1fr))`;
    const rwrap = el("div", "rows");
    const head = el("div", "head");
    head.style.gridTemplateColumns = gridCols;
    head.innerHTML = ev.columns
      .map((c) => `<span>${esc(c)}</span>`)
      .join("");
    rwrap.appendChild(head);
    (ev.rows || []).forEach((row) => {
      const r = el("div", "row");
      r.style.gridTemplateColumns = gridCols;
      r.innerHTML = row.map((v) => `<span>${esc(v)}</span>`).join("");
      rwrap.appendChild(r);
    });
    if (ev.meta) {
      const meta = el("div", "meta");
      meta.append(safeMarkup(ev.meta));
      rwrap.appendChild(meta);
    }
    body.appendChild(rwrap);
  } else if (ev.meta) {
    const mw = el("div", "rows");
    const meta = el("div", "meta");
    meta.append(safeMarkup(ev.meta));
    mw.appendChild(meta);
    body.appendChild(mw);
  }

  $("#panels").appendChild(p);
  $("#panels").scrollTop = $("#panels").scrollHeight;
}

function finishResponse(message, event) {
  message.querySelector(".label").textContent = "Coordinator · catalog-backed reply";
  const products = event.products || [];
  if (products.length) {
    const list = el("ul", "products");
    list.setAttribute("aria-label", "Recommended coffee from the catalog");
    for (const product of products) {
      const item = el("li", "product");
      item.dataset.beanId = product.id;
      const image = document.createElement("img");
      const allowed = ["light", "medium", "dark"].map((r) => `/static/products/coffee-${r}.webp`);
      image.src = allowed.includes(product.image_url) ? product.image_url : allowed[1];
      image.alt = `Illustrative ${product.roast_level} roast coffee packaging`;
      image.width = 160;
      image.height = 160;
      image.loading = "lazy";
      image.addEventListener("error", () => { image.hidden = true; }, { once: true });
      const detail = el("div", "product-detail");
      const title = el("h3");
      title.textContent = product.name;
      const origin = el("p", "product-origin");
      origin.textContent = `${product.origin} · ${product.roast_level} roast`;
      const notes = el("p", "product-notes");
      notes.textContent = (product.flavor_notes || []).join(" · ");
      const price = el("p", "product-price");
      price.textContent = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" })
        .format(product.price_cents / 100);
      const stock = el("span", "product-stock");
      stock.textContent = product.in_stock > 0 ? `${product.in_stock} in stock` : "Out of stock";
      price.append(stock);
      detail.append(title, origin, notes, price);
      item.append(image, detail);
      list.append(item);
    }
    message.append(list);
    message.append(el("p", "product-caption", "Illustrative packaging · catalog price and stock checked for this reply"));
  }
  if (Number.isFinite(event.confidence)) {
    const coverage = Math.max(0, Math.min(100, event.confidence));
    const line = el("div", "confidence");
    line.title = "A heuristic based on available rows and similarity, not a probability that the answer is correct.";
    line.textContent = `Data coverage · ${coverage}/100`;
    message.append(line);
  }
}

emptyTelemetry();
init();
