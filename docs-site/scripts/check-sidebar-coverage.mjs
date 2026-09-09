import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const repoRoot = path.resolve(siteRoot, '..');
const docsRoot = path.join(repoRoot, 'docs');
const astroConfigPath = path.join(siteRoot, 'astro.config.mjs');

function toPosix(filePath) {
  return filePath.split(path.sep).join('/');
}

function normalizeRoute(route) {
  return String(route).split(/[?#]/u, 1)[0].replace(/^\/+|\/+$/gu, '');
}

function documentationRoute(relativePath) {
  const source = toPosix(relativePath).replace(/\.md$/iu, '');
  if (source === 'index') return '';
  if (source === 'architecture') return 'reference/architecture';
  if (source.endsWith('/index')) return source.slice(0, -'/index'.length);
  return source;
}

async function walkMarkdown(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walkMarkdown(absolutePath)));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      files.push(absolutePath);
    }
  }
  return files;
}

function matches(source, pattern) {
  return [...source.matchAll(pattern)].map((match) => normalizeRoute(match[1]));
}

const markdownFiles = await walkMarkdown(docsRoot);
const documentationRoutes = new Set(
  markdownFiles.map((file) => documentationRoute(path.relative(docsRoot, file))),
);
const astroConfig = await readFile(astroConfigPath, 'utf8');
const sidebarSlugs = matches(astroConfig, /\bslug:\s*['"]([^'"]+)['"]/gu);
const sidebarLinks = matches(astroConfig, /\blink:\s*['"](\/[^'"]*)['"]/gu);
const sidebarRoutes = new Set([...sidebarSlugs, ...sidebarLinks]);

const missingRoutes = [...documentationRoutes]
  .filter((route) => !sidebarRoutes.has(route))
  .sort();
const staleSlugs = sidebarSlugs
  .filter((route) => !documentationRoutes.has(route))
  .sort();

if (missingRoutes.length || staleSlugs.length) {
  if (missingRoutes.length) {
    console.error(
      `Documentation pages missing from the sidebar:\n${missingRoutes
        .map((route) => `  /${route}`)
        .join('\n')}`,
    );
  }
  if (staleSlugs.length) {
    console.error(
      `Sidebar slugs without documentation pages:\n${staleSlugs
        .map((route) => `  /${route}`)
        .join('\n')}`,
    );
  }
  process.exitCode = 1;
} else {
  console.log(`Sidebar covers all ${documentationRoutes.size} documentation pages.`);
}
