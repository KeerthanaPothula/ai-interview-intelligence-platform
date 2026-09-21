#!/usr/bin/env node
/**
 * Blocking vulnerability audit of the frontend's PRODUCTION dependencies.
 *
 *   npm run audit        (local and CI run exactly this)
 *
 * Runs `npm audit --omit=dev --json` and fails (exit 1) on any advisory that is
 * not documented in audit-exceptions.json. devDependencies are deliberately not
 * covered here (build/test tooling never ships to users) — the CI workflow
 * reports them separately as non-blocking.
 *
 * Why a script instead of `npm audit --audit-level=...`: a severity threshold
 * silently hides real findings below it, and `npm audit` has no per-advisory
 * ignore list. This gate is fail-closed instead:
 *   - any undocumented advisory, of any severity, fails;
 *   - an unreachable registry / unparseable output fails;
 *   - `npm audit`'s own exit code is not trusted either way — the verdict is
 *     computed from the advisories themselves.
 *
 * Every exception needs id, package, reason and removeWhen (validated below).
 */
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const EXCEPTIONS_PATH = new URL('../audit-exceptions.json', import.meta.url);
const REQUIRED_FIELDS = ['id', 'package', 'reason', 'removeWhen'];

/** Advisory id: the GHSA slug from the advisory URL, else npm's numeric source. */
export function advisoryId(via) {
  const slug = typeof via.url === 'string' ? via.url.split('/').pop() : '';
  return slug || String(via.source);
}

/** Flatten `npm audit --json` into unique advisories (skips "via: <package>" links). */
export function collectAdvisories(report) {
  const found = new Map();
  for (const [pkg, vulnerability] of Object.entries(report.vulnerabilities ?? {})) {
    for (const via of vulnerability.via ?? []) {
      if (typeof via === 'string') continue;
      const id = advisoryId(via);
      found.set(id, {
        id,
        package: via.name ?? pkg,
        severity: via.severity,
        title: via.title,
      });
    }
  }
  return [...found.values()];
}

export function validateExceptions(exceptions) {
  if (!Array.isArray(exceptions)) throw new Error('"exceptions" must be an array');
  const seen = new Set();
  for (const entry of exceptions) {
    for (const field of REQUIRED_FIELDS) {
      if (typeof entry[field] !== 'string' || entry[field].trim() === '') {
        throw new Error(`exception ${JSON.stringify(entry.id)} is missing "${field}"`);
      }
    }
    if (seen.has(entry.id)) throw new Error(`duplicate exception ${entry.id}`);
    seen.add(entry.id);
  }
}

/** Pure verdict function (unit-tested): no I/O. */
export function evaluate(report, exceptions) {
  if (report.error) {
    return { fatal: `npm audit failed: ${report.error.summary ?? report.error.code}` };
  }
  const advisories = collectAdvisories(report);
  const documented = new Set(exceptions.map((entry) => entry.id));
  const totalReported = report.metadata?.vulnerabilities?.total ?? 0;
  return {
    unresolved: advisories.filter((advisory) => !documented.has(advisory.id)),
    accepted: advisories.filter((advisory) => documented.has(advisory.id)),
    stale: exceptions.filter(
      (entry) => !advisories.some((advisory) => advisory.id === entry.id),
    ),
    // npm says something is vulnerable but we could not read any advisory: fail closed.
    unparsed: totalReported > 0 && advisories.length === 0,
  };
}

function main() {
  const { exceptions } = JSON.parse(readFileSync(EXCEPTIONS_PATH, 'utf8'));
  validateExceptions(exceptions);

  const run = spawnSync('npm', ['audit', '--omit=dev', '--json'], {
    encoding: 'utf8',
    shell: process.platform === 'win32', // npm is npm.cmd on Windows
    maxBuffer: 64 * 1024 * 1024,
  });
  let report;
  try {
    report = JSON.parse(run.stdout);
  } catch {
    console.error('Could not parse `npm audit --json` output:');
    console.error(run.stdout || run.stderr || run.error);
    return 1;
  }

  const verdict = evaluate(report, exceptions);
  if (verdict.fatal) {
    console.error(verdict.fatal);
    return 1;
  }

  for (const advisory of verdict.accepted) {
    const entry = exceptions.find((candidate) => candidate.id === advisory.id);
    console.log(
      `documented exception  ${advisory.id}  ${advisory.package} (${advisory.severity})\n` +
        `    ${advisory.title}\n    why: ${entry.reason}\n    remove when: ${entry.removeWhen}`,
    );
  }
  for (const entry of verdict.stale) {
    console.warn(
      `warning: ${entry.id} is in audit-exceptions.json but is no longer reported — delete it.`,
    );
  }
  if (verdict.unparsed) {
    console.error('npm reported vulnerabilities but no advisories could be read.');
    return 1;
  }
  if (verdict.unresolved.length > 0) {
    console.error('\nUnresolved production dependency vulnerabilities:');
    for (const advisory of verdict.unresolved) {
      console.error(
        `  ${advisory.id}  ${advisory.package} (${advisory.severity})  ${advisory.title}`,
      );
    }
    console.error(
      '\nFix by upgrading the package (`npm audit fix`), or — only if it is verifiably not\n' +
        'reachable / has no compatible fix — document it in frontend/audit-exceptions.json.',
    );
    return 1;
  }
  console.log(
    `\nProduction dependency audit passed (${verdict.accepted.length} documented exception(s), 0 unresolved).`,
  );
  return 0;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.exit(main());
}
