import {node, button, api, fixed} from './ui.mjs';
import {createTeachingGraph, traceSearch} from './hnsw-core.mjs?v=20260910.2';

const NS = 'http://www.w3.org/2000/svg';
function svgNode(tag, attributes = {}, text) {
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  if (text !== undefined) element.textContent = text;
  return element;
}

export function mountHnsw(host) {
  let graph, snapshot, frames = [], step = 0, inspected = 0, selectedId;
  let yaw = -0.3, pitch = 0.42, request, generation = 0;
  host.classList.add('hnsw-explorer');
  host.setAttribute('aria-labelledby', 'hnsw-heading');
  const header = node('div', 'heading-row');
  const intro = node('div');
  const heading = node('h2', '', 'How HNSW finds a coffee');
  heading.id = 'hnsw-heading';
  intro.append(node('p', 'hnsw-eyebrow', 'From an embedding to a neighbor'), heading,
    node('p', 'fine-print', 'Follow a query through sparse shortcuts, then explore the closest candidates.'));
  header.append(intro, node('span', 'hnsw-source', 'Real embeddings · illustrated links'));

  const form = node('form', 'hnsw-query');
  form.setAttribute('aria-label', 'HNSW walkthrough query');
  const label = node('label', '', 'Your query');
  const input = node('input');
  input.id = 'hnsw-query'; input.value = 'bergamot'; input.required = true; input.maxLength = 500;
  input.autocomplete = 'off'; label.htmlFor = input.id;
  const submit = node('button', 'action', 'Trace query'); submit.type = 'submit';
  const efLabel = node('label', 'hnsw-ef', 'Candidate limit · ef');
  const ef = node('select'); ef.id = 'hnsw-ef';
  for (const value of [3, 4, 8, 16]) ef.add(new Option(String(value), value));
  ef.value = '4'; efLabel.append(ef);
  const queryField = node('div', 'hnsw-query-field');
  queryField.append(label, input);
  form.append(queryField, efLabel, submit);
  const examples = node('div', 'hnsw-examples');
  examples.append(node('span', '', 'Try'));
  for (const query of ['bergamot', 'chocolate espresso', 'floral and fruity']) {
    examples.append(button(query, () => { input.value = query; load(); }, 'hnsw-example'));
  }
  const status = node('p', 'fine-print hnsw-status');
  status.id = 'hnsw-status'; status.setAttribute('role', 'status');

  const content = node('div', 'hnsw-content'); content.hidden = true;
  const layout = node('div', 'hnsw-layout');
  const scene = node('div', 'hnsw-scene');
  const viewControls = node('div', 'hnsw-view-controls');
  viewControls.setAttribute('aria-label', 'Graph view');
  viewControls.append(button('↶', () => { yaw -= 0.2; renderGraph(); }, 'hnsw-view-button'),
    button('↷', () => { yaw += 0.2; renderGraph(); }, 'hnsw-view-button'),
    button('Reset view', () => { yaw = -0.3; pitch = 0.42; tilt.value = '24'; renderGraph(); }, 'hnsw-view-button'));
  viewControls.children[0].setAttribute('aria-label', 'Rotate graph left');
  viewControls.children[1].setAttribute('aria-label', 'Rotate graph right');
  const tiltLabel = node('label', 'hnsw-tilt', 'Tilt');
  const tilt = node('input'); tilt.type = 'range'; tilt.min = 15; tilt.max = 48; tilt.value = 24;
  tilt.setAttribute('aria-label', 'Graph tilt');
  tilt.addEventListener('input', () => { pitch = Number(tilt.value) * Math.PI / 180; renderGraph(); });
  tiltLabel.append(tilt); viewControls.append(tiltLabel);
  const drawing = svgNode('svg', {viewBox: '0 0 760 590', class: 'hnsw-graph', role: 'group',
    'aria-label': 'Layered 3D HNSW illustration. Use the step controls to follow the search, or the coffee selector below to inspect a node.'});
  const graphScroll = node('div', 'hnsw-graph-scroll'); graphScroll.append(drawing);
  const legend = node('div', 'hnsw-legend');
  for (const [tone, text] of [['query', 'Query'], ['current', 'Current'], ['checked', 'Checked'], ['kept', 'Kept']]) {
    const item = node('span', tone, text); legend.append(item);
  }
  scene.append(viewControls, graphScroll, legend);
  const story = node('div', 'hnsw-story');
  story.setAttribute('aria-live', 'polite');
  const storyCount = node('p', 'hnsw-eyebrow');
  const storyTitle = node('h3');
  const storyText = node('p', 'hnsw-story-text');
  const metrics = node('div', 'hnsw-metrics');
  const candidateHeading = node('h4', '', 'Closest candidates so far');
  const candidates = node('ol', 'hnsw-candidates');
  const outcome = node('p', 'hnsw-outcome'); outcome.hidden = true;
  story.append(storyCount, storyTitle, storyText, metrics, candidateHeading, candidates, outcome);
  layout.append(scene, story);

  const controls = node('div', 'hnsw-step-controls');
  const previous = button('← Previous', () => go(step - 1));
  previous.id = 'hnsw-previous';
  const next = button('Next step →', () => go(step + 1), 'action'); next.id = 'hnsw-next';
  const restart = button('Restart', () => go(0), 'quiet-button');
  const progress = node('input');
  progress.id = 'hnsw-progress'; progress.type = 'range'; progress.min = 0; progress.step = 1;
  progress.setAttribute('aria-label', 'Traversal step');
  progress.addEventListener('input', () => go(Number(progress.value)));
  controls.append(previous, progress, next, restart);

  const inspect = node('div', 'hnsw-inspect');
  const coffeeLabel = node('label', '', 'Inspect a coffee');
  const coffee = node('select'); coffee.id = 'hnsw-coffee'; coffeeLabel.htmlFor = coffee.id;
  const distance = node('p', 'fine-print'); distance.id = 'hnsw-distance';
  coffee.addEventListener('change', () => { inspected = Number(coffee.value); renderInspection(); renderGraph(); });
  inspect.append(coffeeLabel, coffee, distance);
  const notes = node('details', 'hnsw-notes');
  notes.append(node('summary', '', 'What this illustration represents'));
  const explanation = node('p', 'fine-print');
  explanation.textContent = 'Coffee and query embeddings come from the local model and PostgreSQL catalog. Distances use every embedding dimension. The drawing uses two principal components on stacked layers, with small display offsets to separate overlapping nodes; visual spacing is approximate. Layer membership, nearest-neighbor links, and connecting bridges form a deterministic teaching graph; they are not pgvector’s stored graph or an observed index scan. ef here changes this illustration only. Vector proximity does not enforce budget, stock, or origin constraints.';
  const realLink = node('a', '', 'Measure actual pgvector HNSW in Experiments →');
  realLink.href = '/experiments'; realLink.dataset.route = '';
  notes.append(explanation, realLink);
  content.append(layout, controls, inspect, notes);
  host.replaceChildren(header, form, examples, status, content);

  form.addEventListener('submit', event => { event.preventDefault(); load(); });
  input.addEventListener('input', () => {
    input.setCustomValidity('');
    if (snapshot) status.textContent = `Showing “${snapshot.query}”. Trace your edited query to update the walkthrough.`;
  });
  ef.addEventListener('change', () => { if (graph) { frames = traceSearch(graph, Number(ef.value)); go(0); } });

  async function load() {
    input.setCustomValidity(input.value.trim() ? '' : 'Enter a query to trace.');
    if (!form.reportValidity()) return;
    request?.abort(); request = new AbortController();
    const current = ++generation;
    submit.disabled = true; ef.disabled = true; content.hidden = true;
    status.classList.remove('error');
    status.textContent = 'Embedding the query and reading the catalog vectors…';
    try {
      const data = await api('/api/search/walkthrough', {body: {query: input.value.trim()}, signal: request.signal, timeout: 90000});
      if (current !== generation) return;
      const nextGraph = createTeachingGraph(data.products, data.query_embedding);
      graph = nextGraph; snapshot = data;
      frames = traceSearch(graph, Number(ef.value));
      inspected = Math.max(0, graph.products.findIndex(product => product.id === selectedId));
      coffee.replaceChildren(...graph.products.map((product, i) => new Option(`${i + 1}. ${product.name}`, i)));
      content.hidden = false;
      status.textContent = `“${data.query}” · ${data.products.length}${data.truncated ? ` of ${data.total}` : ''} catalog vectors · ${data.query_embedding.length} dimensions · ${data.embedding_model}`;
      if (data.truncated) status.textContent += ' · bounded illustration of the first 48 coffees by name';
      go(0);
    } catch (problem) {
      if (current !== generation || problem.name === 'AbortError') return;
      status.classList.add('error');
      status.textContent = `${problem instanceof SyntaxError ? 'The server did not return a valid walkthrough.' : problem.message} Use Trace query to retry.`;
    } finally {
      if (current === generation) { submit.disabled = false; ef.disabled = false; }
    }
  }
  function go(index) {
    step = Math.max(0, Math.min(frames.length - 1, index));
    const frame = frames[step];
    previous.disabled = step === 0; next.disabled = step === frames.length - 1;
    progress.max = frames.length - 1; progress.value = step;
    progress.setAttribute('aria-valuetext', `Step ${step + 1} of ${frames.length}: ${frame.title}`);
    storyCount.textContent = `Step ${step + 1} / ${frames.length} · Layer ${frame.layer}`;
    storyTitle.textContent = frame.title; storyText.textContent = frame.description;
    metrics.replaceChildren();
    for (const [value, title] of [[`${frame.checked.length} / ${graph.products.length}`, 'coffees checked'], [`${ef.value}`, 'ef · candidate limit']]) {
      const metric = node('div'); metric.append(node('strong', '', value), node('span', '', title)); metrics.append(metric);
    }
    candidates.replaceChildren();
    const listed = frame.phase === 'done' ? frame.results : frame.retained.length ? frame.retained : [frame.current];
    for (const i of listed) {
      const item = node('li');
      item.append(node('span', '', graph.products[i].name), node('b', '', fixed(graph.distances[i], 3)));
      if (frame.results?.includes(i)) item.classList.add('returned');
      candidates.append(item);
    }
    candidateHeading.textContent = frame.phase === 'done' ? `Top ${frame.results.length} returned · cosine distance` : frame.layer > 0 ? 'Best entry point · cosine distance' : 'Closest candidates · cosine distance';
    outcome.hidden = frame.phase !== 'done';
    outcome.textContent = frame.phase === 'done'
      ? `${frame.recovered} / ${frame.exact.length} exhaustive top-${frame.exact.length} neighbors recovered in this teaching graph. ${frame.recovered === frame.exact.length ? 'Try another query or a smaller ef to explore the search.' : 'Increase ef to explore more candidates; recovery is not guaranteed.'}` : '';
    renderInspection(); renderGraph();
  }
  function renderInspection() {
    coffee.value = inspected;
    distance.textContent = `Cosine distance ${fixed(graph.distances[inspected], 4)} · lower is closer to “${snapshot.query}”. Computed in ${snapshot.query_embedding.length} dimensions.`;
  }
  function renderGraph() {
    if (!graph || !frames.length) return;
    const frame = frames[step];
    const checked = new Set(frame.checked), kept = new Set(frame.retained);
    const returned = new Set(frame.results || []);
    const activeLinks = new Set(frame.neighbors.map(i => [frame.from ?? frame.current, i].sort((a, b) => a - b).join('-')));
    const examinedLinks = new Set(frame.examined.map(([a, b, layer]) => `${layer}:${[a, b].sort((x, y) => x - y).join('-')}`));
    function project(x, z, layer) {
      const rx = x * Math.cos(yaw) - z * Math.sin(yaw);
      const rz = x * Math.sin(yaw) + z * Math.cos(yaw);
      const height = (layer - (graph.layers.length - 1) / 2) * 164;
      const depth = rz * 122 * Math.cos(pitch) + height * Math.sin(pitch);
      const perspective = 1000 / (1000 + depth);
      return {x: 380 + rx * 260 * perspective,
        y: 294 + (rz * 122 * Math.sin(pitch) - height * Math.cos(pitch)) * perspective,
        scale: perspective, depth};
    }
    const point = (i, layer) => project(...graph.projection.points[i], layer);
    drawing.replaceChildren();
    const defs = svgNode('defs');
    const gradient = svgNode('radialGradient', {id: 'hnsw-bead', cx: '30%', cy: '25%', r: '80%'});
    gradient.append(svgNode('stop', {offset: '0%', 'stop-color': '#e9e5da'}), svgNode('stop', {offset: '100%', 'stop-color': '#a69d8c'}));
    defs.append(gradient); drawing.append(defs);
    // Layers are drawn from bottom to top. Nodes on each plane are depth sorted.
    for (let layer = 0; layer < graph.layers.length; layer++) {
      const data = graph.layers[layer];
      const group = svgNode('g', {'data-layer': layer, class: `hnsw-layer${frame.layer === layer ? ' active' : ''}`});
      const corners = [[-1.12, -1.1], [1.12, -1.1], [1.12, 1.1], [-1.12, 1.1]].map(([x, z]) => project(x, z, layer));
      group.append(svgNode('polygon', {points: corners.map(p => `${p.x},${p.y}`).join(' '), class: 'hnsw-plane'}));
      for (const [a, b] of data.links) {
        const from = point(a, layer), to = point(b, layer);
        const key = [a, b].sort((x, y) => x - y).join('-');
        const active = layer === frame.layer && activeLinks.has(key);
        group.append(svgNode('line', {x1: from.x, y1: from.y, x2: to.x, y2: to.y,
          class: `hnsw-edge${examinedLinks.has(`${layer}:${key}`) ? ' examined' : ''}${active ? ' examining' : ''}`}));
      }
      if (layer > 0) {
        const from = point(frame.current, layer), to = point(frame.current, layer - 1);
        if (data.members.includes(frame.current)) group.append(svgNode('line', {
          x1: from.x, y1: from.y, x2: to.x, y2: to.y,
          class: `hnsw-descent${frame.phase === 'descend' && frame.fromLayer === layer ? ' active' : ''}`,
        }));
      }
      const positions = data.members.map(i => ({i, ...point(i, layer)})).sort((a, b) => b.depth - a.depth);
      for (const {i, x, y, scale} of positions) {
        const active = frame.current === i && frame.layer === layer;
        const tone = returned.has(i) && layer === 0 ? 'returned' : active ? 'current' : kept.has(i) && layer === 0 ? 'kept' : checked.has(i) ? 'checked' : 'unseen';
        const bead = svgNode('g', {transform: `translate(${x} ${y}) scale(${scale})`, class: `hnsw-node ${tone}${inspected === i ? ' inspected' : ''}`,
          role: 'button', tabindex: '-1', 'aria-label': `${graph.products[i].name}, layer ${layer}, distance ${fixed(graph.distances[i], 4)}`, 'data-node': i});
        bead.append(svgNode('title', {}, `${graph.products[i].name} · cosine distance ${fixed(graph.distances[i], 4)}`),
          svgNode('circle', {r: 14, fill: 'transparent', class: 'hnsw-node-target'}),
          svgNode('ellipse', {cy: 12, rx: 13, ry: 4, fill: '#1c1410', opacity: '.12'}),
          svgNode('circle', {r: 13, class: 'hnsw-bead'}),
          svgNode('circle', {r: 18, class: 'hnsw-node-ring'}),
          svgNode('text', {'text-anchor': 'middle', dy: '4', class: 'hnsw-node-number'}, i + 1));
        if (active && frame.phase !== 'done') bead.append(svgNode('text', {x: 23, y: -14, class: 'hnsw-current-name'}, graph.products[i].name));
        bead.addEventListener('click', () => { inspected = i; renderInspection(); renderGraph(); });
        group.append(bead);
      }
      const q = project(...graph.projection.query, layer);
      const query = svgNode('g', {transform: `translate(${q.x} ${q.y})`, class: `hnsw-query-marker${frame.layer === layer ? ' active' : ''}`});
      query.append(svgNode('path', {d: 'M 0 -12 L 10 0 L 0 12 L -10 0 Z'}),
        svgNode('text', {x: 16, y: 4}, frame.layer === layer ? 'QUERY' : 'q'));
      group.append(query);
      const labelPoint = project(-1.15, 1.22, layer);
      const label = svgNode('text', {x: labelPoint.x, y: labelPoint.y + 18, class: 'hnsw-layer-label'});
      label.textContent = `L${layer}  ·  ${data.members.length} coffees${layer === 0 ? '  ·  best-first' : '  ·  greedy'}`;
      group.append(label); drawing.append(group);
    }
  }
  load();
  return {
    selectProduct(product) {
      selectedId = product.id;
      if (graph) { const i = graph.products.findIndex(p => p.id === product.id); if (i >= 0) { inspected = i; renderInspection(); renderGraph(); } }
    },
    refresh: load,
  };
}
