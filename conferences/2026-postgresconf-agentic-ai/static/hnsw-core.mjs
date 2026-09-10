// A deliberately small teaching topology, not pgvector's stored HNSW graph.
// Search follows greedy upper layers and bounded best-first SEARCH-LAYER:
// https://github.com/pgvector/pgvector/blob/master/src/hnswutils.c
const dot = (a, b) => a.reduce((sum, value, i) => sum + value * b[i], 0);
const norm = a => Math.sqrt(dot(a, a));
function unit(vector) {
  const length = norm(vector);
  if (!vector.length || !vector.every(Number.isFinite) || !length) throw new Error('Embeddings must be finite, nonzero vectors.');
  return vector.map(value => value / length);
}
export const cosineDistance = (a, b) => 1 - Math.max(-1, Math.min(1, dot(unit(a), unit(b))));
const edgeKey = (a, b) => [a, b].sort().join('|');
const stableHash = id => [...id].reduce((hash, letter) => Math.imul(hash ^ letter.charCodeAt(0), 16777619) >>> 0, 2166136261);

// Two principal components determine only the drawing's x/z positions.
// Every search comparison below still uses the full normalized embedding.
function projection(vectors, query) {
  const dimensions = query.length;
  const mean = Array.from({length: dimensions}, (_, i) => vectors.reduce((sum, v) => sum + v[i], 0) / vectors.length);
  const centered = vectors.map(vector => vector.map((value, i) => value - mean[i]));
  const axes = [];
  for (let axis = 0; axis < 2; axis++) {
    let direction = Array.from({length: dimensions}, (_, i) => Math.sin((i + 1) * (axis + 1.7)));
    for (let iteration = 0; iteration < 40; iteration++) {
      const next = Array(dimensions).fill(0);
      for (const row of centered) {
        const score = dot(row, direction);
        for (let i = 0; i < dimensions; i++) next[i] += row[i] * score;
      }
      for (const previous of axes) {
        const overlap = dot(next, previous);
        for (let i = 0; i < dimensions; i++) next[i] -= overlap * previous[i];
      }
      const length = norm(next);
      direction = length > 1e-10 ? next.map(value => value / length) : Array(dimensions).fill(0);
    }
    axes.push(direction);
  }
  const point = vector => axes.map(axis => dot(vector.map((value, i) => value - mean[i]), axis));
  const raw = vectors.map(point);
  const queryPoint = point(query);
  const scale = Math.max(0.01, ...raw.flat().map(Math.abs), ...queryPoint.map(Math.abs));
  const points = raw.map(p => p.map(value => value / scale));
  // Close vectors can overlap after projection. Add small, deterministic
  // display offsets; these coordinates never participate in the search.
  const cosine = Math.cos(-0.3), sine = Math.sin(-0.3);
  const depthScale = 122 * Math.sin(0.42);
  for (let pass = 0; pass < 60; pass++) {
    for (let a = 0; a < points.length; a++) for (let b = a + 1; b < points.length; b++) {
      const dx = points[b][0] - points[a][0], dz = points[b][1] - points[a][1];
      let sx = (dx * cosine - dz * sine) * 260;
      let sy = (dx * sine + dz * cosine) * depthScale;
      let length = Math.hypot(sx, sy);
      if (length >= 38) continue;
      if (length < 1e-8) { sx = Math.cos(a + b) * .01; sy = Math.sin(a + b) * .01; length = .01; }
      const push = (38 - length) / (2 * length);
      const rx = sx * push / 260, rz = sy * push / depthScale;
      const ox = rx * cosine + rz * sine, oz = -rx * sine + rz * cosine;
      for (const [index, direction] of [[a, -1], [b, 1]]) {
        points[index][0] = Math.max(-1.05, Math.min(1.05, points[index][0] + ox * direction));
        points[index][1] = Math.max(-1.05, Math.min(1.05, points[index][1] + oz * direction));
      }
    }
  }
  return {points, query: queryPoint.map(value => value / scale)};
}

export function createTeachingGraph(products, queryEmbedding) {
  if (!products.length) throw new Error('No catalog embeddings are available.');
  const query = unit(queryEmbedding);
  const vectors = products.map(product => {
    if (product.embedding.length !== query.length) throw new Error('The query and catalog embedding dimensions differ.');
    return unit(product.embedding);
  });
  const distances = vectors.map(a => vectors.map(b => 1 - Math.max(-1, Math.min(1, dot(a, b)))));
  const order = products.map((_, i) => i).sort((a, b) => stableHash(products[a].id) - stableHash(products[b].id) || a - b);
  const memberships = [products.map((_, i) => i)];
  if (products.length >= 3) memberships.push(order.slice(0, Math.max(2, Math.ceil(products.length / 3))));
  if (products.length >= 8) memberships.push(order.slice(0, Math.max(2, Math.ceil(products.length / 8))));
  const layers = memberships.map(members => {
    const links = new Map();
    const add = (a, b) => links.set(edgeKey(a, b), [a, b]);
    for (const a of members) {
      const nearest = members.filter(b => b !== a).sort((b, c) => distances[a][b] - distances[a][c] || b - c);
      nearest.slice(0, 3).forEach(b => add(a, b));
    }
    // Join disconnected clusters with their nearest bridge. This makes the
    // small illustration navigable without claiming to reproduce index build.
    const roots = new Map(members.map(i => [i, i]));
    function root(a) { while (roots.get(a) !== a) a = roots.get(a); return a; }
    function join(a, b) { roots.set(root(a), root(b)); }
    for (const [a, b] of links.values()) join(a, b);
    const pairs = members.flatMap((a, i) => members.slice(i + 1).map(b => [a, b]));
    pairs.sort(([a, b], [c, d]) => distances[a][b] - distances[c][d]);
    for (const [a, b] of pairs) if (root(a) !== root(b)) { add(a, b); join(a, b); }
    const neighbors = Object.fromEntries(members.map(i => [i, []]));
    for (const [a, b] of links.values()) { neighbors[a].push(b); neighbors[b].push(a); }
    return {members, links: [...links.values()], neighbors};
  });
  return {products, layers, entry: order[0], projection: projection(vectors, query),
    distances: vectors.map(vector => 1 - Math.max(-1, Math.min(1, dot(query, vector))))};
}

export function traceSearch(graph, ef = 4, k = 3) {
  if (!Number.isInteger(ef) || ef < k || !Number.isInteger(k) || k < 1) throw new Error('ef must be an integer at least as large as k.');
  const {layers, distances, products} = graph;
  const compare = (a, b) => distances[a] - distances[b] || a - b;
  const checked = new Set();
  const examined = [];
  const frames = [];
  let current = graph.entry;
  let frontier = [];
  let retained = [];
  function frame(phase, layer, title, description, extra = {}) {
    frames.push({phase, layer, current, title, description, checked: [...checked],
      examined: examined.map(edge => [...edge]), frontier: [...frontier], retained: [...retained], neighbors: [], ...extra});
  }
  checked.add(current);
  frame('entry', layers.length - 1, 'Start with a sparse layer',
    `Enter at ${products[current].name}. Upper layers contain fewer coffees, so a few comparisons can bring the search near the query.`);
  for (let layer = layers.length - 1; layer > 0; layer--) {
    while (true) {
      const neighbors = layers[layer].neighbors[current];
      for (const neighbor of neighbors) { checked.add(neighbor); examined.push([current, neighbor, layer]); }
      const nearest = [current, ...neighbors].sort(compare)[0];
      const previous = current;
      if (distances[nearest] < distances[current]) {
        current = nearest;
        frame('move', layer, 'Follow the closer neighbor',
          `${products[current].name} is closer to the query than ${products[previous].name}. Stay on this layer and inspect its links.`,
          {from: previous, neighbors});
      } else {
        frame('settled', layer, 'No closer neighbor here',
          'None of the linked coffees improves the cosine distance. Continue from this same coffee in the denser layer below.',
          {neighbors});
        break;
      }
    }
    frame('descend', layer - 1, 'Descend without starting over',
      `${products[current].name} also exists on layer ${layer - 1}. It becomes the entry point for the next search.`,
      {fromLayer: layer});
  }
  const visited = new Set([current]);
  frontier = [current];
  retained = [current];
  frame('base', 0, 'Keep several promising candidates',
    `At layer 0, switch to best-first search. Keep up to ${ef} candidates (ef), instead of committing to one greedy path.`);
  while (frontier.length) {
    frontier.sort(compare);
    const next = frontier.shift();
    if (retained.length >= ef && distances[next] > distances[retained.at(-1)]) break;
    current = next;
    const neighbors = [];
    for (const neighbor of layers[0].neighbors[current]) {
      if (visited.has(neighbor)) continue;
      visited.add(neighbor); checked.add(neighbor);
      examined.push([current, neighbor, 0]); neighbors.push(neighbor);
      if (retained.length < ef || distances[neighbor] < distances[retained.at(-1)]) {
        frontier.push(neighbor);
        retained.push(neighbor);
        retained.sort(compare);
        if (retained.length > ef) retained.pop();
      }
    }
    frame('expand', 0, 'Explore the best candidate next',
      `Inspect ${products[current].name}${neighbors.length ? ` and ${neighbors.length} unchecked neighbor${neighbors.length === 1 ? '' : 's'}` : '; its neighbors have already been checked'}. The retained list holds the closest ${Math.min(ef, retained.length)} candidates found so far.`,
      {neighbors});
  }
  const results = retained.slice(0, k);
  const exact = products.map((_, i) => i).sort(compare).slice(0, k);
  frame('done', 0, 'Return the nearest candidates found',
    'The remaining frontier cannot improve the retained set, or has been exhausted. Return the best candidates found, and compare them with an exhaustive search.',
    {results, exact, recovered: results.filter(i => exact.includes(i)).length});
  return frames;
}
