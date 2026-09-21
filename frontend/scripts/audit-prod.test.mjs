// @vitest-environment node
// Pure Node logic (fs, real file: URLs) — the default jsdom environment swaps in a
// browser URL class that node:fs rejects.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  advisoryId,
  collectAdvisories,
  evaluate,
  validateExceptions,
} from './audit-prod.mjs';

const advisory = (id, name = 'left-pad', severity = 'moderate') => ({
  source: 1,
  name,
  title: `${id} title`,
  url: `https://github.com/advisories/${id}`,
  severity,
});

/** Minimal `npm audit --json` report containing the given advisories. */
const report = (...advisories) => ({
  vulnerabilities: {
    'left-pad': { via: advisories },
    // A dependent package only links to the advisory-bearing package by name.
    consumer: { via: ['left-pad'] },
  },
  metadata: { vulnerabilities: { total: advisories.length } },
});

const documented = (id) => ({ id, package: 'left-pad', reason: 'r', removeWhen: 'w' });

describe('production npm audit verdict', () => {
  it('passes a clean report', () => {
    const verdict = evaluate({ vulnerabilities: {}, metadata: { vulnerabilities: { total: 0 } } }, []);
    expect(verdict.unresolved).toEqual([]);
    expect(verdict.unparsed).toBe(false);
  });

  it('fails on an undocumented advisory, whatever its severity', () => {
    for (const severity of ['low', 'moderate', 'high', 'critical']) {
      const verdict = evaluate(report(advisory('GHSA-aaaa-bbbb-cccc', 'x', severity)), []);
      expect(verdict.unresolved.map((a) => a.id)).toEqual(['GHSA-aaaa-bbbb-cccc']);
    }
  });

  it('accepts only the documented advisory, not the whole package', () => {
    const verdict = evaluate(
      report(advisory('GHSA-known-known-known'), advisory('GHSA-new0-new0-new0')),
      [documented('GHSA-known-known-known')],
    );
    expect(verdict.accepted.map((a) => a.id)).toEqual(['GHSA-known-known-known']);
    expect(verdict.unresolved.map((a) => a.id)).toEqual(['GHSA-new0-new0-new0']);
  });

  it('flags exceptions that are no longer reported so they get removed', () => {
    const verdict = evaluate(report(), [documented('GHSA-gone-gone-gone')]);
    expect(verdict.stale.map((e) => e.id)).toEqual(['GHSA-gone-gone-gone']);
  });

  it('fails closed when npm reports vulnerabilities but no advisory can be read', () => {
    const verdict = evaluate(
      { vulnerabilities: { pkg: { via: ['other'] } }, metadata: { vulnerabilities: { total: 1 } } },
      [],
    );
    expect(verdict.unparsed).toBe(true);
  });

  it('fails when npm audit itself errored (e.g. registry unreachable)', () => {
    const verdict = evaluate({ error: { code: 'ENOTFOUND', summary: 'offline' } }, []);
    expect(verdict.fatal).toMatch(/offline/);
  });

  it('identifies advisories by their GHSA slug, falling back to the numeric source', () => {
    expect(advisoryId({ url: 'https://github.com/advisories/GHSA-1234-5678-9abc', source: 9 })).toBe(
      'GHSA-1234-5678-9abc',
    );
    expect(advisoryId({ source: 4242 })).toBe('4242');
    expect(collectAdvisories(report(advisory('GHSA-1234-5678-9abc')))).toHaveLength(1);
  });
});

describe('audit-exceptions.json', () => {
  const { exceptions } = JSON.parse(
    readFileSync(new URL('../audit-exceptions.json', import.meta.url), 'utf8'),
  );

  it('documents every exception with a reason and a removal condition', () => {
    expect(() => validateExceptions(exceptions)).not.toThrow();
  });

  it('rejects an exception without a removal condition', () => {
    expect(() => validateExceptions([{ id: 'X', package: 'p', reason: 'r' }])).toThrow(/removeWhen/);
  });

  it('rejects duplicate exceptions', () => {
    expect(() => validateExceptions([documented('X'), documented('X')])).toThrow(/duplicate/);
  });
});
