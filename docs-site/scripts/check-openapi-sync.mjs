import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const repoRoot = path.resolve(siteRoot, '..');
const sourcePath = path.join(repoRoot, 'docs', 'openapi.json');
const publishedPath = path.join(siteRoot, 'public', 'openapi.json');

async function readArtifact(artifactPath) {
  try {
    return await readFile(artifactPath);
  } catch (error) {
    console.error(`Failed to read ${path.relative(repoRoot, artifactPath)}.`);
    throw error;
  }
}

const [source, published] = await Promise.all([
  readArtifact(sourcePath),
  readArtifact(publishedPath),
]);

if (!source.equals(published)) {
  console.error('docs-site/public/openapi.json is out of sync with docs/openapi.json.');
  console.error('Run `npm --prefix docs-site run sync:docs` and commit the updated artifact.');
  process.exit(1);
}

console.log('docs-site/public/openapi.json is in sync with docs/openapi.json.');
