// Keep the dark diagrams structurally identical to their paper originals.
import {readFile, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const colors = {
  '#f6f1e8': '#080707',
  '#fffbf4': '#16110e',
  '#cbb9a4': '#8d7e67',
  '#6b5d52': '#d7cebf',
  '#1c1410': '#f4eddf',
  '#3f5c4b': '#eee2cc',
  '#e8eee5': '#211810',
  '#efe6d8': '#251a12',
  '#ead9cf': '#281b12',
  '#6b3f2a': '#f2e5cf',
  '#d7cabb': '#84725c',
  '#9e8f7d': '#d1c0a6',
  '#c87830': '#e0be81',
  '#925422': '#e0be81',
  '#e2d6c6': '#3a2d24',
};

for (const name of ['hnsw-layers', 'ndcg']) {
  const source = new URL(`assets/${name}.svg`, import.meta.url);
  const destination = new URL(`assets/${name}-dark.svg`, import.meta.url);
  const original = await readFile(source, 'utf8');
  const dark = original.replace(/#[0-9a-f]{6}\b/gi, color => colors[color.toLowerCase()] ?? color);
  await writeFile(destination, dark);
  console.log(`Prepared ${fileURLToPath(destination)}`);
}
