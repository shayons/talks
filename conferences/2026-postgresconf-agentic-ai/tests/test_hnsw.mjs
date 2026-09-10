import test from 'node:test';
import assert from 'node:assert/strict';
import {createTeachingGraph, traceSearch, cosineDistance} from '../static/hnsw-core.mjs';

const products = Array.from({length: 24}, (_, i) => ({
  id: `coffee-${i}`, name: `Coffee ${i}`,
  embedding: [Math.cos(i * .31), Math.sin(i * .31), (i % 5) * .13, .5],
}));

test('layers are nested, links stay within each layer, and construction is deterministic', () => {
  const graph = createTeachingGraph(products, [1, .4, .2, .5]);
  assert.deepEqual(graph, createTeachingGraph(products, [1, .4, .2, .5]));
  assert.equal(graph.layers.length, 3);
  for (const [level, layer] of graph.layers.entries()) {
    for (const [a, b] of layer.links) {
      assert.ok(layer.members.includes(a) && layer.members.includes(b));
      assert.ok(layer.neighbors[a].includes(b) && layer.neighbors[b].includes(a));
    }
    if (level) assert.ok(layer.members.every(i => graph.layers[level - 1].members.includes(i)));
  }
  assert.ok(graph.layers.at(-1).members.includes(graph.entry));
});

test('moves follow a real link toward a smaller full-vector distance; descents keep the entry', () => {
  const query = [1, .4, .2, .5];
  const graph = createTeachingGraph(products, query);
  graph.distances.forEach((value, i) => assert.ok(Math.abs(value - cosineDistance(query, products[i].embedding)) < 1e-12));
  const frames = traceSearch(graph, 4);
  for (const [i, frame] of frames.entries()) {
    if (frame.phase === 'move') {
      assert.ok(graph.layers[frame.layer].neighbors[frame.from].includes(frame.current));
      assert.ok(graph.distances[frame.current] < graph.distances[frame.from]);
    }
    if (frame.phase === 'descend') {
      assert.equal(frame.current, frames[i - 1].current);
      assert.equal(frame.layer, frame.fromLayer - 1);
    }
    for (const [a, b, level] of frame.examined) assert.ok(graph.layers[level].neighbors[a].includes(b));
    assert.ok(frame.retained.length <= 4);
    assert.ok(frame.retained.every(node => frame.checked.includes(node)));
  }
});

test('full-width search recovers exhaustive neighbors and every retained list is sorted', () => {
  for (const query of [[1, 0, .3, .5], [-1, .2, .6, .5], [.2, -1, 0, .5]]) {
    const graph = createTeachingGraph(products, query);
    const frames = traceSearch(graph, products.length);
    const end = frames.at(-1);
    assert.deepEqual(end.results, end.exact);
    assert.equal(end.recovered, 3);
    for (const frame of frames) for (let i = 1; i < frame.retained.length; i++) {
      assert.ok(graph.distances[frame.retained[i - 1]] <= graph.distances[frame.retained[i]]);
    }
  }
});

test('handles tiny catalogs and rejects invalid embeddings and search widths', () => {
  const graph = createTeachingGraph(products.slice(0, 1), [1, 0, 0, .5]);
  assert.deepEqual(traceSearch(graph).at(-1).results, [0]);
  assert.ok(graph.projection.points.flat().every(Number.isFinite));
  assert.throws(() => createTeachingGraph([], [1, 0]), /No catalog/);
  assert.throws(() => createTeachingGraph(products, [1, 0]), /dimensions differ/);
  assert.throws(() => createTeachingGraph(products, [0, 0, 0, 0]), /nonzero/);
  assert.throws(() => traceSearch(graph, 2), /ef must/);
});
