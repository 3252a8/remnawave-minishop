import { readFile, writeFile } from 'node:fs/promises';

// Nova 0.12.3 unconditionally enables this transformer. Drop the patch once
// the theme exposes its Twoslash option. Keep all other Shiki transformers.
const entry = new URL(import.meta.resolve('starlight-theme-nova'));
const source = await readFile(entry, 'utf8');
const enabled = 'createShikiConfig({ twoslash: true })';
const disabled = 'createShikiConfig({ twoslash: false })';

if (source.includes(enabled)) {
  await writeFile(entry, source.replace(enabled, disabled));
} else if (!source.includes(disabled)) {
  throw new Error('Review the Nova Twoslash patch for the installed theme.');
}
