import {$, error} from './ui.mjs';
import {closePersonaBrief} from './persona-brief.mjs?v=20260910.2';

const routes = {'/': 'lab', '/catalog': 'catalog', '/experiments': 'experiments', '/concierge': 'concierge'};
const modules = {};
let generation = 0;
async function showRoute(focus = false) {
  closePersonaBrief();
  const current = ++generation;
  const view = routes[location.pathname] || 'lab';
  document.body.dataset.view = view;
  document.querySelectorAll('[id^="view-"]').forEach(section => { section.hidden = section.id !== `view-${view}`; });
  document.querySelectorAll('.main-nav a').forEach(link => {
    if (link.pathname === location.pathname) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.title = `Coffee & queries · ${view === 'lab' ? 'PostgreSQL Search Lab' : view[0].toUpperCase() + view.slice(1)} · Postgres Summit US 2026`;
  if (focus) { window.scrollTo(0, 0); $('#main-content').focus({preventScroll: true}); }
  try {
    if (view === 'concierge') await (modules.concierge ||= import('./app.js?v=20260910.2'));
    else {
      const module = await (modules[view] ||= import(`./${view}-ui.js?v=20260910.4`));
      if (current === generation) await module.activate();
    }
  } catch (problem) {
    delete modules[view];
    // Keep the page intact so retrying a module does not destroy its controls.
    let notice = $(`#view-${view} > .load-error`);
    if (!notice) { notice = document.createElement('div'); notice.className = 'load-error'; $(`#view-${view}`).prepend(notice); }
    error(notice, problem, () => { notice.remove(); showRoute(); });
  }
}
document.addEventListener('click', event => {
  const link = event.target.closest('a[data-route]');
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  if (location.pathname !== link.pathname) history.pushState({}, '', link.pathname);
  showRoute(true);
});
window.addEventListener('popstate', () => showRoute(true));
showRoute();
