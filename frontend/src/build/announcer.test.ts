import { describe, expect, it } from 'vitest';
import { announcerWithoutInlineStyle } from './announcer';

type Hooks = {
  buildStart: (this: unknown) => void;
  transform: (this: unknown, code: string, id: string) => { code: string } | null;
  buildEnd: (this: unknown, error?: Error) => void;
};

const WITH_STYLE =
  '<div id="svelte-announcer" aria-live="assertive" style="position: absolute; left: 0"></div>';

/** One plugin, as one `vite build` uses it, with a fake client and a fake ssr build. */
function setup() {
  const hooks = announcerWithoutInlineStyle() as unknown as Hooks;
  const client = { environment: { name: 'client' } };
  const ssr = { environment: { name: 'ssr' } };
  return { hooks, client, ssr };
}

describe('the announcer without its inline style', () => {
  it('removes the style attribute and passes when both builds find it', () => {
    const { hooks, client, ssr } = setup();
    for (const build of [ssr, client]) {
      hooks.buildStart.call(build);
      const out = hooks.transform.call(build, WITH_STYLE, '/x/root.svelte');
      expect(out?.code).not.toContain('style=');
      expect(out?.code).toContain('id="svelte-announcer"');
      expect(() => hooks.buildEnd.call(build)).not.toThrow();
    }
  });

  it('fails the browser build that never finds it, even if the ssr build did', () => {
    const { hooks, client, ssr } = setup();
    hooks.buildStart.call(ssr);
    hooks.transform.call(ssr, WITH_STYLE, '/x/root.svelte');
    hooks.buildEnd.call(ssr);
    hooks.buildStart.call(client);
    hooks.transform.call(client, 'const nothing = 1;', '/x/other.js');
    expect(() => hooks.buildEnd.call(client)).toThrow(/not found in the browser build/);
  });

  it('does not let an earlier build cover for a later one that skips it', () => {
    const { hooks, client } = setup();
    hooks.buildStart.call(client);
    hooks.transform.call(client, WITH_STYLE, '/x/root.svelte');
    hooks.buildEnd.call(client);
    hooks.buildStart.call(client); // a second build, which skips it
    expect(() => hooks.buildEnd.call(client)).toThrow(/not found/);
  });

  it('fails when the markup changes so the style can no longer be removed', () => {
    const { hooks, client } = setup();
    hooks.buildStart.call(client);
    expect(() =>
      hooks.transform.call(client, '<div id="svelte-announcer" ' + "{...attrs}></div>", '/x/a.svelte')
    ).toThrow(/markup has changed/);
  });

  it('leaves other files alone, and does not hide an earlier error', () => {
    const { hooks, client } = setup();
    hooks.buildStart.call(client);
    expect(hooks.transform.call(client, 'svelte-announcer', '/x/style.css')).toBeNull();
    expect(() => hooks.buildEnd.call(client, new Error('another'))).not.toThrow();
  });
});
