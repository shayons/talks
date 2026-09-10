import {$, node, button, money, fixed, code, api, error, download, methodRows, METHODS, LABELS, REGULARS, regularSearch} from './ui.mjs';

let initialized = false;
let stage = null;
let stageBusy = false;
let roundRevision = 0;
let rounds = [];
let picks = {};
let revealed = false;
let fixtureResult = null;

export async function activate() {
  if (!initialized) {
    initialized = true;
    $('#blind-refresh').addEventListener('click', newRound);
    $('#blind-reveal').addEventListener('click', () => { revealed = true; renderRounds(); });
    $('#price-raise').addEventListener('click', () => priceChange('raise'));
    $('#price-restore').addEventListener('click', () => priceChange('restore'));
    $('#index-prepare').addEventListener('click', prepare);
    $('#index-compare').addEventListener('click', compare);
    for (const selector of ['#index-ef', '#index-filter', '#index-iterative']) $(selector).addEventListener('input', () => {
      if (fixtureResult) $('#index-status').textContent = 'Settings changed. Compare again to measure these settings; the result below keeps its original settings.';
    });
    await Promise.all([refreshStage(), newRound()]);
  } else if (!stageBusy) await refreshStage();
}
async function refreshStage() {
  try {
    stage = await api('/api/experiments/status');
    $('#stage-status').textContent = stage.enabled ? 'Presenter controls are enabled on this server.' : 'Presenter controls are off on this server. Blind judging is available; price and index controls require the presenter’s local setup.';
    updateStage();
  } catch (problem) { stage = null; updateStage(); error($('#stage-status'), problem, refreshStage); }
}
function updateStage() {
  const enabled = stage?.enabled && !stageBusy;
  $('#price-raise').disabled = !enabled || stage.price.active || stage.price.current_cents !== 1900;
  $('#price-restore').disabled = !enabled || !stage.price.active;
  $('#index-prepare').disabled = !enabled || stage.fixture.ready;
  $('#index-compare').disabled = !enabled || !stage.fixture.ready;
  for (const selector of ['#index-ef', '#index-filter', '#index-iterative']) $(selector).disabled = !enabled;
  if (stage) {
    $('#price-current').textContent = stage.price.current_cents == null ? 'Coffee missing from catalog' : `Current price: ${money(stage.price.current_cents)}`;
    $('#fixture-status').textContent = stage.fixture.ready ? `${stage.fixture.rows.toLocaleString()} vectors ready · ${stage.fixture.dimensions} dimensions · seed ${stage.fixture.seed}` : `Fixture not prepared · ${stage.fixture.target_rows.toLocaleString()} vectors will be created separately from the coffee catalog.`;
  }
}
function shuffle(values) {
  const result = [...values];
  for (let i = result.length - 1; i > 0; i--) {
    const random = crypto.getRandomValues(new Uint32Array(1))[0] / 2 ** 32;
    const j = Math.floor(random * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
async function newRound() {
  const current = ++roundRevision;
  $('#blind-refresh').disabled = true;
  $('#blind-reveal').disabled = true;
  $('#blind-status').textContent = 'Retrieving three comparisons from PostgreSQL…';
  $('#blind-rounds').replaceChildren();
  $('#blind-summary').textContent = '';
  try {
    const results = await Promise.all(REGULARS.map(regular => api('/api/search', {body: regularSearch(regular), timeout: 90000})));
    if (current !== roundRevision) return;
    rounds = results.map((run, index) => ({run, regular: REGULARS[index], methods: shuffle(METHODS)}));
    picks = {};
    revealed = false;
    $('#blind-status').textContent = 'Each round uses the same filters across all three methods. An empty list is a valid choice.';
    renderRounds();
  } catch (problem) { if (current === roundRevision) error($('#blind-status'), problem, newRound); }
  finally { if (current === roundRevision) $('#blind-refresh').disabled = false; }
}
function renderRounds() {
  $('#blind-rounds').replaceChildren();
  for (const {run, regular, methods} of rounds) {
    const round = node('section', 'blind-round');
    round.append(node('h3', '', `${regular.name} — “${regular.request}”`));
    const options = node('div', 'blind-options');
    methods.forEach((method, index) => {
      const control = button('', () => {
        if (revealed) return;
        picks[regular.id] = method;
        options.querySelectorAll('button').forEach((choice, i) => choice.setAttribute('aria-pressed', i === index));
        $('#blind-reveal').disabled = Object.keys(picks).length !== rounds.length;
        $('#blind-summary').textContent = `${Object.keys(picks).length} of ${rounds.length} choices made`;
      }, 'blind-choice');
      control.setAttribute('aria-pressed', picks[regular.id] === method);
      control.setAttribute('aria-label', `${regular.name}, list ${'ABC'[index]}${revealed ? `, ${LABELS[method]}` : ''}`);
      control.append(node('span', 'blind-label', revealed ? `List ${'ABC'[index]} · ${LABELS[method]}${picks[regular.id] === method ? ' · your pick' : ''}` : `List ${'ABC'[index]}`));
      const rows = methodRows(run, method).slice(0, 5);
      const list = node('ol');
      rows.forEach(product => list.append(node('li', '', product.name)));
      control.append(rows.length ? list : node('p', 'fine-print', 'No eligible results.'));
      options.append(control);
    });
    round.append(options); $('#blind-rounds').append(round);
  }
  $('#blind-reveal').disabled = revealed || Object.keys(picks).length !== rounds.length;
  $('#blind-summary').textContent = revealed ? REGULARS.map(regular => `${regular.name}: ${LABELS[picks[regular.id]]}`).join(' · ') : 'Choose one list for each regular.';
}
function rankingSummary(label, run) {
  const panel = node('section', 'evidence-block');
  panel.append(node('h3', '', label), node('p', 'fine-print', `${run.eligible_count} eligible coffees · top hybrid results`));
  const list = node('ol');
  run.results.slice(0, 4).forEach(product => list.append(node('li', '', `${product.name} · ${money(product.price_cents)}`)));
  panel.append(list);
  const target = run.results.find(product => product.id === 'b_ethiopia_yirg');
  const excluded = run.excluded.find(product => product.id === 'b_ethiopia_yirg');
  panel.append(node('p', target ? '' : 'fine-print', target ? `Yirgacheffe is eligible at ${money(target.price_cents)}.` : excluded ? `Yirgacheffe: ${excluded.reasons.join('; ')}.` : 'Yirgacheffe is not in the candidate lists.'));
  return panel;
}
async function priceChange(action) {
  if (stageBusy) return;
  stageBusy = true; updateStage();
  $('#price-status').textContent = 'Reading the current ranking…';
  $('#price-results').replaceChildren();
  let changed = false;
  try {
    const before = await api('/api/search', {body: regularSearch(REGULARS[0]), timeout: 90000});
    $('#price-status').textContent = action === 'raise' ? 'Updating the catalog price…' : 'Restoring the original price…';
    stage.price = await api('/api/experiments/price', {body: {action}});
    changed = true;
    window.dispatchEvent(new Event('catalog-changed'));
    const after = await api('/api/search', {body: regularSearch(REGULARS[0]), timeout: 90000});
    $('#price-results').append(rankingSummary('Before the change', before), rankingSummary('After the change', after));
    $('#price-status').textContent = `Catalog price ${action === 'raise' ? 'raised' : 'restored'}. The ranking above was recomputed from PostgreSQL.`;
    $('#blind-status').textContent = 'The catalog price changed. Start a new round to refresh blind judging; existing choices refer to the earlier snapshot.';
  } catch (problem) {
    error($('#price-status'), new Error(`${changed ? 'The price was saved, but the comparison could not finish. ' : ''}${problem.message}`));
  } finally {
    await refreshStage();
    // A disconnected response can hide a committed mutation. Invalidate cached
    // search evidence even when the mutation's response was not received.
    if (!changed) window.dispatchEvent(new Event('catalog-changed'));
    stageBusy = false;
    updateStage();
  }
}
async function prepare() {
  if (stageBusy) return;
  stageBusy = true; updateStage();
  $('#index-status').textContent = 'Preparing 12,000 vectors and building the HNSW index. This may take up to two minutes…';
  try {
    stage.fixture = await api('/api/experiments/index/prepare', {body: {}, timeout: 150000});
    $('#index-status').textContent = `Fixture ready in ${fixed(stage.fixture.prepare_ms / 1000, 1)} seconds. Choose settings, then compare.`;
  } catch (problem) { error($('#index-status'), problem); }
  finally { await refreshStage(); stageBusy = false; updateStage(); }
}
async function compare() {
  if (stageBusy || !$('#index-ef').reportValidity()) return;
  const settings = {ef_search: Number($('#index-ef').value), filtered: $('#index-filter').checked, iterative: $('#index-iterative').checked};
  stageBusy = true; updateStage();
  $('#index-status').textContent = 'Executing exact and HNSW queries with EXPLAIN ANALYZE…';
  $('#index-results').replaceChildren();
  try {
    fixtureResult = await api('/api/experiments/index/compare', {body: settings, timeout: 90000});
    renderComparison(fixtureResult);
    $('#index-status').textContent = fixtureResult.hnsw_used ? 'Verified: the approximate query used points_hnsw.' : 'The query did not use the HNSW index. Inspect its plan before interpreting this comparison.';
  } catch (problem) { fixtureResult = null; error($('#index-status'), problem); }
  finally { stageBusy = false; updateStage(); }
}
function renderComparison(result) {
  const host = $('#index-results');
  const metrics = node('div', 'metric-row');
  for (const [label, value] of [['Recall @20', result.recall == null ? '—' : `${fixed(result.recall * 100, 1)}%`], ['Recovered neighbors', `${result.recovered} / ${result.reference_count}`], ['Exact SQL', `${fixed(result.exact.query_ms, 2)} ms`], ['HNSW SQL', `${fixed(result.hnsw.query_ms, 2)} ms`]]) {
    const metric = node('span', '', label); metric.append(node('strong', '', value)); metrics.append(metric);
  }
  host.append(metrics, node('p', 'fine-print', `${result.fixture_rows.toLocaleString()} fixture rows · ${result.eligible_rows.toLocaleString()} eligible · ef_search ${result.settings.ef_search} · iterative scan ${result.settings.iterative ? 'on' : 'off'}`));
  const table = node('table', 'neighbor-table');
  table.append(node('caption', 'sr-only', 'Exact and approximate nearest neighbors, in rank order'));
  const head = node('thead'); const headings = node('tr');
  ['Rank', 'Exact ID', 'HNSW ID', 'Recovered'].forEach(text => { const cell = node('th', '', text); cell.scope = 'col'; headings.append(cell); });
  head.append(headings); table.append(head);
  const body = node('tbody');
  const exactIds = new Set(result.exact.rows.map(row => row.id));
  for (let i = 0; i < Math.max(result.exact.rows.length, result.hnsw.rows.length); i++) {
    const row = node('tr'); const ann = result.hnsw.rows[i];
    [i + 1, result.exact.rows[i]?.id ?? '—', ann?.id ?? '—', ann ? exactIds.has(ann.id) ? 'Yes' : 'No' : '—'].forEach(text => row.append(node('td', '', text)));
    body.append(row);
  }
  table.append(body); host.append(table, node('p', 'fine-print', result.measurement_note));
  for (const [name, plan] of [['Exact', result.exact.plan], ['HNSW', result.hnsw.plan]]) {
    const details = node('details'); details.append(node('summary', '', `${name} execution plan`), code(JSON.stringify(plan, null, 2))); host.append(details);
  }
  const sql = node('details'); sql.append(node('summary', '', 'Fixture query'), code(result.sql));
  host.append(sql, button('Download index comparison', () => download('coffee-index-comparison.json', result)));
}
