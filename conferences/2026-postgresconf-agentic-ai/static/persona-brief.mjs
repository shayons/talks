import {node, button} from './ui.mjs';

let dialog;

// Previewing a person never changes the active request, customer, or session.
export function showPersonaBrief({name, title, portrait, personality, preferences, request, lesson, actionLabel, onChoose}) {
  if (!dialog) {
    dialog = node('dialog', 'persona-brief');
    dialog.id = 'persona-brief';
    dialog.setAttribute('aria-labelledby', 'persona-name');
    dialog.setAttribute('aria-describedby', 'persona-personality');
    document.body.append(dialog);
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const controls = [...dialog.querySelectorAll('button:not(:disabled)')];
      const first = controls[0];
      const last = controls.at(-1);
      if (event.shiftKey && (document.activeElement === first || document.activeElement.id === 'persona-name')) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
    });
  }
  const header = node('div', 'brief-header');
  const intro = node('div', 'brief-intro');
  const heading = node('h2', '', name);
  heading.id = 'persona-name';
  heading.tabIndex = -1;
  heading.autofocus = true;
  const about = node('p', 'brief-personality', personality);
  about.id = 'persona-personality';
  intro.append(node('p', 'brief-eyebrow', 'Meet the regular'), heading, node('p', 'brief-role', title), about);
  if (portrait) {
    const image = node('img', 'brief-portrait');
    image.src = portrait;
    image.alt = '';
    header.append(image);
  }
  header.append(intro);
  const body = node('div', 'brief-body');
  if (preferences) body.append(node('h3', '', 'Coffee preferences'), node('p', '', preferences));
  body.append(node('h3', '', 'The first question'), node('blockquote', '', `“${request}”`),
    node('h3', '', 'What to watch'), node('p', '', lesson));
  const footer = node('div', 'brief-footer');
  const close = button('Close', () => dialog.close());
  footer.append(close, button(actionLabel, () => { dialog.close(); onChoose(); }, 'action'));
  dialog.replaceChildren(header, body, node('p', 'brief-note', 'Fictional demo persona · illustrative portrait'), footer);
  dialog.showModal();
}

export const personaBriefOpen = () => Boolean(dialog?.open);

export function closePersonaBrief() {
  if (dialog?.open) dialog.close();
}
