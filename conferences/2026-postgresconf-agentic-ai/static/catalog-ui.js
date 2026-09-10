import {$, node, button, bag, money, fixed, chip, code, api, error, download} from './ui.mjs';
import {mountHnsw} from './hnsw-ui.js?v=20260910.2';

let initialized = false;
let products = [];
let selected = null;
let revision = 0;
let walkthrough;

export async function activate() {
  if (!initialized) {
    initialized = true;
    $('#catalog-refresh').addEventListener('click', () => { activate(); walkthrough?.refresh(); });
  }
  const current = ++revision;
  $('#catalog-status').textContent = 'Reading the PostgreSQL catalog…';
  $('#catalog-refresh').disabled = true;
  try {
    const data = await api('/api/catalog');
    if (current !== revision) return;
    products = data.products;
    $('#catalog-status').textContent = `${data.total} coffees · ${data.embedding_model}${data.truncated ? ` · showing the first ${products.length}` : ''}`;
    if (!products.some(product => product.id === selected)) selected = products[0]?.id;
    renderList();
    $('#catalog-hnsw').hidden = !products.length;
    if (!walkthrough && products.length) walkthrough = mountHnsw($('#catalog-hnsw'));
    if (selected) await loadDetail(selected);
    else $('#catalog-detail').replaceChildren(node('p', '', 'The catalog is empty. Add coffee data to explore its search evidence.'));
  } catch (problem) { if (current === revision) error($('#catalog-status'), problem, activate); }
  finally { $('#catalog-refresh').disabled = false; }
}
function renderList() {
  $('#catalog-list').replaceChildren();
  for (const product of products) {
    const control = button('', () => {
      loadDetail(product.id);
      if (matchMedia('(max-width: 640px)').matches) $('#catalog-detail').scrollIntoView({block: 'start'});
    }, 'coffee-hit');
    control.dataset.coffee = product.id;
    control.setAttribute('aria-pressed', selected === product.id);
    const content = node('span', 'hit-content');
    content.append(node('strong', '', product.name), node('span', 'hit-meta', `${product.origin} · ${product.roast_level}`));
    const chips = node('span', 'chips');
    product.flavor_notes.slice(0, 3).forEach(note => chips.append(chip(note)));
    if (product.in_stock <= 0) chips.append(chip('Out of stock'));
    content.append(chips);
    control.append(bag(product), content, node('span', 'catalog-price', money(product.price_cents)));
    $('#catalog-list').append(control);
  }
}
async function loadDetail(id) {
  selected = id;
  document.querySelectorAll('[data-coffee]').forEach(control => control.setAttribute('aria-pressed', control.dataset.coffee === id));
  const current = ++revision;
  const host = $('#catalog-detail');
  host.replaceChildren(node('p', 'fine-print', 'Loading this coffee’s search evidence…'));
  try {
    const product = await api(`/api/catalog/${encodeURIComponent(id)}`);
    if (current !== revision) return;
    walkthrough?.selectProduct(product);
    host.replaceChildren();
    const head = node('div', 'coffee-detail-head');
    const heading = node('div');
    heading.append(node('h2', '', product.name), node('p', 'fine-print', product.origin));
    head.append(bag(product), heading);
    const facts = node('dl', 'detail-facts');
    for (const [label, value] of [['Roast', product.roast_level], ['Process', product.process], ['Price / bag', money(product.price_cents)], ['In stock', `${product.in_stock} bags`]]) {
      const fact = node('div'); fact.append(node('dt', '', label), node('dd', '', value)); facts.append(fact);
    }
    const notes = node('div', 'chips');
    product.flavor_notes.forEach(note => notes.append(chip(note, 'hybrid')));
    host.append(head, facts, node('p', '', product.description), notes, node('h3', '', 'Weighted text document'));
    for (const [weight, values] of Object.entries(product.weighted_fields)) {
      const block = node('div', 'evidence-block');
      block.append(node('strong', 'fine-print', weight === 'A' ? 'A · name, origin, flavor notes' : 'B · description'), node('p', '', values.join(' · ')));
      host.append(block);
    }
    const document = node('details');
    document.append(node('summary', '', 'Stored tsvector · lexemes, positions, weights'), code(product.search_document || '(empty)', true));
    host.append(document, node('h3', '', 'Semantic embedding'));
    if (product.embedding) {
      const vector = product.embedding;
      host.append(node('p', 'fine-print', `${vector.length} learned dimensions · ${product.embedding_model}. Color shows sign and magnitude; dimensions do not have flavor labels.`));
      const grid = node('div', 'vector-grid');
      grid.setAttribute('role', 'img');
      grid.setAttribute('aria-label', `${vector.length}-dimension embedding heatmap. Exact numeric values are available below.`);
      const max = Math.max(...vector.map(Math.abs), 0.000001);
      vector.forEach((value, index) => {
        const cell = node('span', 'vector-cell');
        cell.title = `Dimension ${index + 1}: ${fixed(value, 6)}`;
        cell.style.backgroundColor = value >= 0 ? 'var(--vector)' : 'var(--primary)';
        cell.style.opacity = 0.15 + 0.85 * Math.abs(value) / max;
        grid.append(cell);
      });
      const values = node('details');
      values.append(node('summary', '', 'Inspect all dimension values'), code(vector.map((value, i) => `${String(i + 1).padStart(3)}  ${fixed(value, 7)}`).join('\n')));
      host.append(grid, values, button('Download coffee evidence', () => download(`coffee-${product.id}.json`, product)));
      host.append(button('Follow a query through HNSW →', () => $('#catalog-hnsw').scrollIntoView({block: 'start'}), 'action hnsw-jump'));
    } else host.append(node('p', 'fine-print', 'This coffee has no embedding. It can still match through full-text search.'));
    host.append(node('p', 'fine-print', 'Illustrative packaging. Product facts and search evidence are read from PostgreSQL.'));
  } catch (problem) { if (current === revision) error(host, problem, () => loadDetail(id)); }
}
