import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  demoAdminRoutes,
  demoPublicRoutes,
  demoRuntimeRoutes,
} from '../src/lib/demoRoutes.mjs';

const siteRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const registryPath = path.join(siteRoot, '..', 'frontend', 'src', 'admin', 'sections', 'registry.ts');
const source = await readFile(registryPath, 'utf8');
const sectionsStart = source.indexOf('const CORE_ADMIN_SECTIONS:');
const sectionsEnd = source.indexOf('\n];', sectionsStart);
if (sectionsStart < 0 || sectionsEnd < 0) {
  throw new Error('Could not read CORE_ADMIN_SECTIONS from the admin section registry.');
}
const sectionIds = [...source.slice(sectionsStart, sectionsEnd).matchAll(/^    id: "([a-z_]+)",/gm)].map(
  (match) => match[1],
);
if (!sectionIds.length) throw new Error('No core admin section IDs found in the registry.');

const missing = sectionIds.filter((id) => !demoAdminRoutes.includes(id));
const stale = demoAdminRoutes.filter((id) => !sectionIds.includes(id));
const duplicate = demoAdminRoutes.filter((id, index) => demoAdminRoutes.indexOf(id) !== index);
const unmaterialized = demoAdminRoutes.filter(
  (id) => !demoPublicRoutes.includes(`admin/${id}`) || !demoRuntimeRoutes.includes(`admin/${id}`),
);

if (missing.length || stale.length || duplicate.length || unmaterialized.length) {
  if (missing.length) console.error(`Admin sections missing demo routes: ${missing.join(', ')}`);
  if (stale.length) console.error(`Demo routes without admin sections: ${stale.join(', ')}`);
  if (duplicate.length) console.error(`Duplicate demo routes: ${duplicate.join(', ')}`);
  if (unmaterialized.length) console.error(`Demo routes not materialized: ${unmaterialized.join(', ')}`);
  process.exitCode = 1;
} else {
  console.log(`Demo routes cover all ${sectionIds.length} core admin sections.`);
}
