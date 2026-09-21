import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import indexHtml from '../../index.html?raw';
import { ThemeProvider, useTheme } from './ThemeContext';

const root = document.documentElement;
const themeColor = () => document.querySelector('meta[name="theme-color"]')?.getAttribute('content');

function Probe() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button type="button" onClick={toggleTheme}>
      {theme}
    </button>
  );
}

// Node 22+'s built-in `localStorage` shadows jsdom's and lacks clear()/setItem
// semantics (see api/client.test.ts) — stub a plain in-memory Storage instead.
function fakeStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, String(v)),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
  };
}

beforeEach(() => {
  document.head.insertAdjacentHTML('beforeend', '<meta name="theme-color" content="#070C18">');
  vi.stubGlobal('localStorage', fakeStorage());
  root.removeAttribute('data-theme');
});

afterEach(() => {
  document.querySelector('meta[name="theme-color"]')?.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('index.html no-flash script', () => {
  // Runs the real inline script with injected storage/matchMedia globals.
  const script = /<script>([\s\S]*?)<\/script>/.exec(indexHtml)![1];
  const run = (storage: Pick<Storage, 'getItem'>, matchMedia?: () => { matches: boolean }) =>
    new Function('localStorage', 'matchMedia', script)(storage, matchMedia);
  const osLight = () => ({ matches: true });
  const osDark = () => ({ matches: false });
  const stored = (v: string | null) => ({ getItem: () => v });

  it('defaults to dark when nothing is stored and the OS prefers dark', () => {
    run(stored(null), osDark);
    expect(root.dataset.theme).toBe('dark');
    expect(themeColor()).toBe('#070C18');
  });

  it('follows the OS light preference when nothing is stored', () => {
    run(stored(null), osLight);
    expect(root.dataset.theme).toBe('light');
    expect(themeColor()).toBe('#F6F8FC');
  });

  it('prefers the persisted theme over the OS', () => {
    run(stored('dark'), osLight);
    expect(root.dataset.theme).toBe('dark');
    run(stored('light'), osDark);
    expect(root.dataset.theme).toBe('light');
  });

  it('ignores a garbage stored value', () => {
    run(stored('purple'), osLight);
    expect(root.dataset.theme).toBe('light');
  });

  it('still honors the OS when localStorage throws', () => {
    run({ getItem: () => { throw new Error('blocked'); } }, osLight);
    expect(root.dataset.theme).toBe('light');
  });

  it('falls back to dark when matchMedia is unavailable', () => {
    run(stored(null), undefined);
    expect(root.dataset.theme).toBe('dark');
  });
});

describe('ThemeProvider', () => {
  it.each(['dark', 'light'] as const)('reads the initial %s theme from <html>', (initial) => {
    root.setAttribute('data-theme', initial);
    render(<ThemeProvider><Probe /></ThemeProvider>);
    expect(screen.getByRole('button')).toHaveTextContent(initial);
  });

  it('toggles light <-> dark, persisting under aiip-theme and updating theme-color', async () => {
    root.setAttribute('data-theme', 'dark');
    render(<ThemeProvider><Probe /></ThemeProvider>);
    await userEvent.click(screen.getByRole('button'));
    expect(root.dataset.theme).toBe('light');
    expect(localStorage.getItem('aiip-theme')).toBe('light');
    expect(themeColor()).toBe('#F6F8FC');
    await userEvent.click(screen.getByRole('button'));
    expect(root.dataset.theme).toBe('dark');
    expect(localStorage.getItem('aiip-theme')).toBe('dark');
    expect(themeColor()).toBe('#070C18');
  });

  it('keeps DOM and React state in sync when localStorage.setItem throws', async () => {
    root.setAttribute('data-theme', 'dark');
    vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    render(<ThemeProvider><Probe /></ThemeProvider>);
    await userEvent.click(screen.getByRole('button'));
    expect(root.dataset.theme).toBe('light');
    expect(screen.getByRole('button')).toHaveTextContent('light');
  });

  it('follows aiip-theme changes from another tab and ignores unrelated events', () => {
    root.setAttribute('data-theme', 'dark');
    render(<ThemeProvider><Probe /></ThemeProvider>);
    const fire = (key: string | null, newValue: string | null) =>
      act(() => {
        window.dispatchEvent(new StorageEvent('storage', { key, newValue }));
      });

    fire('aiip-theme', 'light');
    expect(root.dataset.theme).toBe('light');
    expect(screen.getByRole('button')).toHaveTextContent('light');

    fire('other-key', 'dark');
    fire('aiip-theme', 'purple');
    fire('aiip-theme', null);
    fire(null, null); // localStorage.clear()
    expect(root.dataset.theme).toBe('light');
  });

  it('removes its storage listener on unmount', () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');
    const { unmount } = render(<ThemeProvider><Probe /></ThemeProvider>);
    const handler = add.mock.calls.find(([type]) => type === 'storage')![1];
    unmount();
    expect(remove).toHaveBeenCalledWith('storage', handler);
  });
});
