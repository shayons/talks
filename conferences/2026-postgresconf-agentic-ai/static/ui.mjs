export const $ = (selector) => document.querySelector(selector);
export function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
export function button(text, action, className = 'quiet-button') {
  const element = node('button', className, text);
  element.type = 'button';
  element.addEventListener('click', action);
  return element;
}
export const money = cents => new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD'}).format(cents / 100);
export const fixed = (number, digits = 3) => Number(number).toFixed(digits);
export const chip = (text, tone = '') => node('span', `chip ${tone}`, text);
export function bag(product) {
  const image = node('img');
  const paths = ['light', 'medium', 'dark'].map(roast => `/static/products/coffee-${roast}.webp`);
  image.src = paths.includes(product.image_url) ? product.image_url : paths[1];
  image.alt = ''; // Decorative: the adjacent text identifies the coffee.
  image.width = 64;
  image.height = 80;
  image.loading = 'lazy';
  return image;
}
export function code(text, wrap = false) {
  const pre = node('pre', wrap ? 'code-wrap' : '');
  pre.tabIndex = 0;
  pre.append(node('code', '', text));
  return pre;
}
export async function api(path, {body, signal, timeout = 30000} = {}) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the entered values and try again.');
  return data;
}
export function error(host, problem, retry) {
  host.replaceChildren(node('p', 'error', problem.name === 'TimeoutError' ? 'The request timed out. Please retry.' : problem.message));
  if (retry) host.append(button('Retry', retry));
}
export function download(name, data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
  const link = node('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function copy(text, control) {
  try { await navigator.clipboard.writeText(text); control.textContent = 'Copied'; }
  catch { control.textContent = 'Select the text below to copy'; }
}
export function methodRows(run, method) {
  if (method === 'keyword') return run.results.filter(row => row.lexical_rank != null).sort((a, b) => a.lexical_rank - b.lexical_rank);
  if (method === 'vector') return run.results.filter(row => row.semantic_rank != null).sort((a, b) => a.semantic_rank - b.semantic_rank);
  return run.results;
}
export const METHODS = ['keyword', 'vector', 'hybrid'];
export const LABELS = {keyword: 'Keyword', vector: 'Vector', hybrid: 'Hybrid'};
export const REGULARS = [
  {id: 'leo', name: 'Leo', title: 'Pour-over explorer', personality: 'Curious about bright, fragrant coffees, with a clear budget in mind. He knows the flavor he wants and wants help finding it at the right price.', request: 'Bergamot with a $20 maximum', lesson: 'Combine flavor evidence with a price constraint. Excluded word matches stay visible.', portrait: 'marco', query: 'bergamot', budget: 2000, origins: []},
  {id: 'maya', name: 'Maya', title: 'Espresso loyalist', personality: 'Practical about her daily espresso, but led by taste rather than coffee terminology. She asks for something that feels like dessert and leaves the flavor matching to the shop.', request: 'Something like dessert', lesson: 'Related flavors can rank even when the exact word is absent.', portrait: 'ana', query: 'dessert', budget: null, origins: []},
  {id: 'yuki', name: 'Yuki', title: 'Origin enthusiast', personality: 'Careful and curious about where coffee comes from. When she asks for Japan, the origin matters; a similar-tasting coffee from somewhere else is a different offer.', request: 'Coffee from Japan', lesson: 'An empty result is useful. A similar flavor cannot satisfy an origin constraint.', portrait: 'yuki', query: 'coffee from Japan', budget: null, origins: ['Japan']},
];
export const regularSearch = regular => ({query: regular.query, budget: regular.budget, origins: regular.origins, roasts: [], stock_only: true, fuzzy: false, candidates: 8, rrf_k: 60, min_cosine: null});
