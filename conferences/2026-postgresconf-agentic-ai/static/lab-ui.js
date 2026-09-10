import {$, node, button, bag, money, fixed, chip, code, api, error, copy, download, methodRows, METHODS, LABELS, REGULARS, regularSearch} from './ui.mjs?v=20260910';
import {showPersonaBrief, personaBriefOpen} from './persona-brief.mjs?v=20260910.2';

let initialized = false;
let catalog = null;
let readiness = null;
let run = null;
let selected = null;
let budget = 2000;
let inspector = 'explain';
let request = null;
let revision = 0;
let timer;
let dirty = false;
let planRevision = 0;

function settings() {
  return {query: $('#lab-query').value.trim(), budget, roasts: $('#lab-roast').value ? [$('#lab-roast').value] : [],
    origins: $('#lab-origin').value ? [$('#lab-origin').value] : [], stock_only: $('#lab-stock').checked,
    fuzzy: $('#lab-fuzzy').checked, candidates: Number($('#lab-candidates').value), rrf_k: Number($('#lab-rrf').value),
    min_cosine: $('#lab-cosine').value === '' ? null : Number($('#lab-cosine').value)};
}
function markRegular(id) {
  document.querySelectorAll('.lab-regular').forEach(control => control.setAttribute('aria-pressed', control.dataset.regular === id));
}
function applyRegular(regular) {
  const value = regularSearch(regular);
  budget = value.budget;
  $('#lab-query').value = value.query;
  $('#lab-budget').value = budget == null ? 50 : budget / 100;
  $('#budget-value').textContent = budget == null ? 'None' : money(budget);
  $('#lab-origin').value = value.origins[0] || '';
  $('#lab-roast').value = '';
  $('#lab-stock').checked = true;
  $('#lab-fuzzy').checked = false;
  $('#lab-candidates').value = 8;
  $('#lab-rrf').value = 60;
  $('#lab-cosine').value = '';
  selected = null;
  markRegular(regular.id);
  invalidate();
  search();
}
function previewRegular(regular) {
  showPersonaBrief({
    ...regular,
    portrait: `/static/portraits/${regular.portrait}.jpg`,
    actionLabel: 'Compare this request',
    onChoose: () => { applyRegular(regular); $('#lab-query').focus({preventScroll: true}); },
  });
}
function invalidate() {
  clearTimeout(timer);
  request?.abort();
  revision++;
  planRevision++;
  run = null;
  $('#search-results').replaceChildren();
  $('#search-results').removeAttribute('aria-busy');
  $('#inspector-content').replaceChildren(node('p', 'fine-print', 'Run the current request to inspect its evidence.'));
}
function changed() {
  invalidate();
  markRegular(null);
  $('#search-status').textContent = $('#lab-query').value.trim() ? 'Request changed. Updating the comparison…' : 'Write a request or choose a regular to compare the three methods.';
  timer = setTimeout(search, 400);
}
export async function activate() {
  if (!initialized) { initialize(); initialized = true; }
  if (!catalog || dirty) {
    try {
      [catalog, readiness] = await Promise.all([api('/api/catalog'), api('/api/search/status')]);
      const origin = $('#lab-origin').value;
      const origins = [...new Set(['Japan', ...catalog.products.map(product => product.origin.split(',').at(-1).trim())])].sort();
      $('#lab-origin').replaceChildren(new Option('Any origin', ''), ...origins.map(value => new Option(value, value)));
      if (origin && !origins.includes(origin)) $('#lab-origin').add(new Option(origin, origin));
      $('#lab-origin').value = origin;
      dirty = false;
    } catch (problem) { error($('#search-status'), problem, activate); return; }
    await search();
  }
}
function initialize() {
  for (const regular of REGULARS) {
    const control = button('', () => previewRegular(regular), 'lab-regular');
    control.dataset.regular = regular.id;
    control.setAttribute('aria-haspopup', 'dialog');
    control.setAttribute('aria-controls', 'persona-brief');
    control.setAttribute('aria-pressed', regular.id === 'leo');
    const portrait = node('img');
    portrait.src = `/static/portraits/${regular.portrait}.jpg`;
    portrait.alt = '';
    const text = node('span', 'regular-copy');
    text.append(node('strong', '', regular.name), node('span', 'role', regular.title), node('span', 'request', `“${regular.request}”`), node('span', 'lesson', `Meet ${regular.name} ↗`));
    control.append(portrait, text);
    $('#lab-regulars').append(control);
  }
  $('#search-form').addEventListener('submit', event => { event.preventDefault(); clearTimeout(timer); search(); });
  $('#search-form').addEventListener('input', event => {
    if (event.target.id === 'lab-budget') { budget = Math.round(Number(event.target.value) * 100); $('#budget-value').textContent = money(budget); }
    changed();
  });
  $('#clear-budget').addEventListener('click', () => { budget = null; $('#lab-budget').value = 50; $('#budget-value').textContent = 'None'; changed(); });
  $('#write-own').addEventListener('click', () => {
    applyRegular({...REGULARS[0], id: null, query: '', budget: null});
    $('#lab-query').focus();
  });
  document.querySelectorAll('[data-method]').forEach(control => control.addEventListener('click', () => {
    $('#search-results').dataset.mobileMethod = control.dataset.method;
    document.querySelectorAll('[data-method]').forEach(item => item.setAttribute('aria-pressed', item === control));
  }));
  document.querySelectorAll('[data-inspector]').forEach(control => control.addEventListener('click', () => {
    inspector = control.dataset.inspector;
    renderInspector();
  }));
  window.addEventListener('keydown', event => {
    if (personaBriefOpen()) return;
    if (document.body.dataset.view !== 'lab' || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    if (event.key === '/') { event.preventDefault(); $('#lab-query').focus(); }
    if (/^[123]$/.test(event.key)) previewRegular(REGULARS[Number(event.key) - 1]);
    if (event.key === 'Escape') { selected = null; renderResults(); renderInspector(); }
  });
  window.addEventListener('catalog-changed', () => { dirty = true; invalidate(); if (document.body.dataset.view === 'lab') activate(); });
}
async function search() {
  clearTimeout(timer);
  const options = settings();
  if (!options.query) { invalidate(); $('#search-status').textContent = 'Write a request or choose a regular to compare the three methods.'; return; }
  if (!$('#search-form').checkValidity()) { $('#search-form').reportValidity(); return; }
  request?.abort();
  request = new AbortController();
  const current = ++revision;
  $('#search-status').textContent = 'Embedding the request and querying PostgreSQL…';
  $('#search-results').setAttribute('aria-busy', 'true');
  try {
    const result = await api('/api/search', {body: options, signal: request.signal, timeout: 90000});
    if (current !== revision) return;
    run = result;
    $('#search-status').textContent = `Eligible ${run.eligible_count}${catalog ? ` / ${catalog.total}` : ''} · text query ${run.parsed_query || '(no lexical tokens)'} · SQL ${fixed(run.timing.query_ms, 2)} ms · embedding ${fixed(run.timing.embedding_ms, 2)} ms. Select a coffee to inspect it.`;
    renderResults();
    renderInspector();
  } catch (problem) {
    if (current !== revision || problem.name === 'AbortError') return;
    run = null;
    $('#search-results').replaceChildren();
    error($('#search-status'), problem, search);
    renderInspector();
  } finally { if (current === revision) $('#search-results').removeAttribute('aria-busy'); }
}
function selectCoffee(id) {
  selected = id;
  inspector = 'explain';
  // Update selection in place to preserve keyboard focus on the clicked card.
  document.querySelectorAll('[data-hit]').forEach(control => control.setAttribute('aria-pressed', control.dataset.hit === id));
  renderInspector();
  $('#inspector').scrollIntoView({block: 'start'});
}
function renderResults() {
  const host = $('#search-results');
  host.replaceChildren();
  if (!run) return;
  for (const method of METHODS) {
    const rows = methodRows(run, method);
    const section = node('section', `paper ranking-column ${method}`);
    const header = node('header');
    const heading = node('div');
    heading.append(node('h2', '', LABELS[method]), node('p', 'fine-print', method === 'keyword' ? 'tsvector · ts_rank_cd' : method === 'vector' ? 'pgvector · cosine similarity' : `Reciprocal Rank Fusion · k=${run.settings.rrf_k}`));
    header.append(heading, node('span', 'fine-print', rows.length));
    section.append(header);
    const list = node('ol', 'hit-list');
    rows.forEach((product, index) => {
      const item = node('li');
      const control = button('', () => selectCoffee(product.id), 'coffee-hit');
      control.dataset.hit = product.id;
      control.setAttribute('aria-pressed', selected === product.id);
      const content = node('span', 'hit-content');
      content.append(node('strong', '', product.name), node('span', 'hit-meta', `${product.origin} · ${product.roast_level} · ${money(product.price_cents)}`));
      const chips = node('span', 'chips');
      if (method === 'keyword') {
        chips.append(chip(`rank ${fixed(product.lexical_score)}`, 'keyword'));
        if (product.trigram_score > 0) chips.append(chip(`trgm ${fixed(product.trigram_score)}`));
      } else if (method === 'vector') {
        chips.append(chip(`cos ${fixed(product.score)}`, 'vector'), ...product.flavor_notes.slice(0, 2).map(note => chip(note)));
      } else chips.append(chip(`RRF ${fixed(product.hybrid_score, 4)}`, 'hybrid'), chip(`kw ${product.lexical_rank ?? '—'}`, 'keyword'), chip(`vec ${product.semantic_rank ?? '—'}`, 'vector'));
      content.append(chips);
      if (method === 'keyword' && product.match_excerpt?.length) {
        const excerpt = node('span', 'excerpt');
        excerpt.style.display = 'block';
        product.match_excerpt.forEach(part => excerpt.append(node(part.highlight ? 'mark' : 'span', '', part.text)));
        content.append(excerpt);
      }
      if (method === 'hybrid') content.append(node('span', 'formula', formula(product)));
      control.append(node('span', 'rank', index + 1), bag(product), content);
      item.append(control); list.append(item);
    });
    section.append(list);
    if (!rows.length) {
      const empty = node('div', 'empty-result');
      empty.append(node('strong', '', method === 'keyword' ? 'No word matches' : method === 'vector' ? 'No eligible neighbors' : 'Empty is useful'),
        node('p', '', method === 'keyword' ? 'No keyword candidates pass this request and its filters.' : 'No coffee entered this ranking with the current filters and retrieval settings.'));
      section.append(empty);
    }
    if (method === 'keyword' && run.excluded.length) {
      const excluded = node('div', 'excluded');
      excluded.append(node('strong', 'fine-print', `Word matches excluded by filters (${run.excluded_total})`));
      run.excluded.forEach(product => excluded.append(button(`${product.name} · ${product.reasons.join('; ')}`, () => selectCoffee(product.id), 'text-button')));
      if (run.excluded_total > run.excluded.length) excluded.append(node('p', 'fine-print', `Showing the first ${run.excluded.length} exclusions.`));
      section.append(excluded);
    }
    host.append(section);
  }
}
function formula(product) {
  const k = run.settings.rrf_k;
  return `${product.lexical_rank ? `1/(${k}+${product.lexical_rank})` : '0'} + ${product.semantic_rank ? `1/(${k}+${product.semantic_rank})` : '0'}`;
}
function renderInspector() {
  document.querySelectorAll('[data-inspector]').forEach(control => control.setAttribute('aria-pressed', control.dataset.inspector === inspector));
  const host = $('#inspector-content');
  host.replaceChildren();
  if (!run) { host.append(node('p', 'fine-print', 'Run a search to inspect its evidence.')); return; }
  if (inspector === 'sql') {
    host.append(node('p', 'fine-print', 'The parameterized statement executed by PostgreSQL. The embedding parameter is a model-produced vector; all other bound values appear below.'));
    const control = button('Copy SQL', () => copy(run.sql, control));
    host.append(control, code(run.sql), code(JSON.stringify(run.settings, null, 2)));
    if (readiness) {
      const details = node('details');
      details.append(node('summary', '', `Indexes · PostgreSQL ${readiness.postgres_version}`), code(readiness.indexes.map(index => index.definition + ';').join('\n\n')));
      host.append(details);
    }
    const excluded = node('details');
    excluded.append(node('summary', '', 'Excluded word matches · diagnostic SQL'), code(run.excluded_sql));
    host.append(excluded);
  } else if (inspector === 'export') {
    host.append(node('p', '', 'Take the query, settings, ranks, exclusions, timings, and any captured plan with you.'), button('Download comparison JSON', () => download('coffee-search-comparison.json', {captured_at: new Date().toISOString(), ...run}), 'action'));
  } else if (inspector === 'plan') {
    host.append(node('p', 'fine-print', 'EXPLAIN ANALYZE executes the query again. On a small catalog PostgreSQL may correctly prefer a sequential scan. Timings describe this server and this execution.'));
    if (run.plan) host.append(code(JSON.stringify(run.plan, null, 2)));
    host.append(button(run.plan ? 'Refresh execution plan' : 'Run EXPLAIN ANALYZE', loadPlan, 'action'));
  } else {
    const product = run.results.find(row => row.id === selected);
    const excluded = run.excluded.find(row => row.id === selected);
    const bean = product || catalog?.products.find(row => row.id === selected) || excluded;
    if (!bean) { host.append(node('p', 'fine-print', 'Select a coffee in any list to see its eligibility, rank contributions, and RRF arithmetic.')); return; }
    const grid = node('div', 'two-columns');
    const facts = node('div');
    facts.append(node('h3', '', bean.name), node('p', 'fine-print', `${bean.origin || ''} · ${money(bean.price_cents)}`), node('p', '', bean.description || ''));
    const tags = node('div', 'chips');
    (bean.flavor_notes || []).forEach(note => tags.append(chip(note)));
    const eligible = node('div', 'evidence-block');
    eligible.append(node('strong', '', 'Eligibility'), node('p', excluded ? 'error' : '', excluded ? excluded.reasons.join('. ') : 'Passes every shared filter.'));
    facts.append(tags, eligible);
    const evidence = node('div');
    for (const [label, text] of [
      ['Keyword', product?.lexical_rank ? `Rank ${product.lexical_rank} · ts_rank_cd ${fixed(product.lexical_score, 5)}${product.text_match ? ' · full-text match' : ' · trigram name match'}` : excluded ? 'Matched the words, failed the filters.' : 'Not in the keyword candidate list.'],
      ['Vector', product?.semantic_rank ? `Rank ${product.semantic_rank} · cosine ${fixed(product.score, 5)}` : 'Not in the vector candidate list.'],
      ['Reciprocal Rank Fusion', product ? `${formula(product)} = ${fixed(product.hybrid_score, 6)} · hybrid rank ${run.results.indexOf(product) + 1}` : 'No contribution: excluded coffees never enter fusion.'],
    ]) { const block = node('div', `evidence-block ${label === 'Reciprocal Rank Fusion' ? 'fusion-block' : ''}`); block.append(node('strong', '', label), node('p', '', text)); evidence.append(block); }
    evidence.append(node('p', 'fine-print', `Equal branch weights. A missing rank contributes zero. Semantic scores use ${run.embedding_model}; individual dimensions are learned features, not named flavors.`));
    grid.append(facts, evidence); host.append(grid);
  }
}
async function loadPlan(event) {
  const snapshot = run;
  const current = ++planRevision;
  const control = event.currentTarget;
  control.disabled = true;
  control.textContent = 'Measuring execution…';
  try {
    const result = await api('/api/search', {body: {...snapshot.settings, explain: true}, timeout: 90000});
    if (current !== planRevision || run !== snapshot) return;
    run = result;
    $('#search-status').textContent = `Refreshed comparison with EXPLAIN · eligible ${run.eligible_count} · SQL ${fixed(run.timing.query_ms, 2)} ms.`;
    renderResults(); renderInspector();
  } catch (problem) {
    if (current !== planRevision || run !== snapshot) return;
    control.disabled = false;
    control.textContent = 'Retry EXPLAIN ANALYZE';
    const message = node('p', 'error', problem.message);
    control.after(message);
  }
}
