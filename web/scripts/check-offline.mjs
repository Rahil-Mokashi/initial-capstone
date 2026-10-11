// Build gate: fails if any built text file references an http(s):// URL that is not
// local. The app must work with no internet, so nothing may point outside 127.0.0.1.
// Run automatically by `npm run build`; also callable: node scripts/check-offline.mjs <dir>
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';

const TEXT = new Set([
  '.html',
  '.js',
  '.mjs',
  '.css',
  '.json',
  '.svg',
  '.map',
  '.txt',
  '.webmanifest',
]);
const LOCAL = /^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$/;
// XML/SVG namespace identifiers are labels, not network requests. Kept explicit and tiny.
const NAMESPACES = new Set([
  'http://www.w3.org/2000/svg',
  'http://www.w3.org/1999/xhtml',
  'http://www.w3.org/1998/Math/MathML',
  'http://www.w3.org/1999/xlink',
  'http://www.w3.org/XML/1998/namespace',
  'http://www.w3.org/2000/xmlns/',
]);
// Text that merely APPEARS inside bundled library JavaScript (error-message doc links,
// JSON-schema dialect ids, an IPv6 host template). Nothing fetches these. Matched exactly and
// only in .js files - HTML and CSS get no allowance. The real enforcement is the CSP and the
// Electron request blocker; this gate catches anything that would be a real dependency.
const INERT_IN_JS = [
  /^https:\/\/react\.dev\/errors\//,
  /^https:\/\/reactrouter\.com\/en\/main\/routers\/picking-a-router$/,
  // Inside a React Router warning message about old browsers ("...load a polyfill such as <url>").
  /^https:\/\/github\.com\/ungap\/url-search-params$/,
  /^https?:\/\/json-schema\.org\/draft[-/][\w-]+\/schema#?$/,
  /^http:\/\/\[\$\{\w+\}\]$/,
];
const URL_PATTERN = /https?:\/\/[^\s"'`)<>\\]+/gi;

export function findExternalUrls(text, { isJs = false } = {}) {
  const hits = [];
  for (const match of text.matchAll(URL_PATTERN)) {
    const url = match[0].replace(/[.,;]+$/, '');
    if (NAMESPACES.has(url)) continue;
    if (isJs && INERT_IN_JS.some((re) => re.test(url))) continue;
    let host;
    try {
      host = new URL(url).host;
    } catch {
      host = url;
    }
    if (!LOCAL.test(host)) hits.push(url);
  }
  return hits;
}

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) yield* walk(full);
    else yield full;
  }
}

export function scan(dir) {
  const problems = [];
  for (const file of walk(dir)) {
    if (!TEXT.has(extname(file).toLowerCase())) continue;
    for (const url of findExternalUrls(readFileSync(file, 'utf8'), {
      isJs: /\.m?js$/i.test(file),
    })) {
      problems.push({ file: relative(dir, file), url });
    }
  }
  return problems;
}

const isMain =
  process.argv[1] &&
  resolve(process.argv[1]) ===
    resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
if (isMain) {
  const dir = resolve(process.argv[2] ?? 'dist');
  const problems = scan(dir);
  if (problems.length > 0) {
    console.error(`OFFLINE CHECK FAILED: ${problems.length} external URL(s) in the build output:`);
    for (const p of problems) console.error(`  ${p.file}: ${p.url}`);
    process.exit(1);
  }
  console.log(`Offline check passed: no external http(s) URLs in ${dir}`);
}
