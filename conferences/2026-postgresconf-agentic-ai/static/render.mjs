// Rebuild a small formatting vocabulary. Never attach provider HTML to the page.
const ALLOWED = new Set(["B", "STRONG", "EM", "I", "P", "BR", "UL", "OL", "LI", "CODE", "CITE"]);
const DROP = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "SVG", "MATH", "TEMPLATE"]);

export function safeMarkup(raw, citationKeys = new Set()) {
  const template = document.createElement("template");
  template.innerHTML = String(raw ?? "");
  const fragment = document.createDocumentFragment();
  function copy(source, target) {
    for (const node of source.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        target.append(document.createTextNode(node.textContent));
      } else if (node.nodeType === Node.ELEMENT_NODE && !DROP.has(node.tagName)) {
        if (!ALLOWED.has(node.tagName)) {
          copy(node, target);
          continue;
        }
        const clean = document.createElement(node.tagName.toLowerCase());
        const key = node.getAttribute("data-k");
        if (node.tagName === "CITE" && citationKeys.has(key)) {
          clean.dataset.k = key;
          clean.tabIndex = 0;
          clean.title = `Postgres row · ${key}`;
        }
        copy(node, clean);
        target.append(clean);
      }
    }
  }
  copy(template.content, fragment);
  return fragment;
}
