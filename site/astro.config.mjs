import { defineConfig } from 'astro/config';
import createSitemap from '@astrojs/sitemap';

// Astro 4 does not emit astro:routes:resolved and uses empty pathname for index;
// normalize routes and index pathname before build:done
const sitemap = () => {
  const integration = createSitemap();
  const buildDone = integration.hooks['astro:build:done'];
  integration.hooks['astro:build:done'] = async (opts) => {
    integration.hooks['astro:routes:resolved']?.({ routes: [] });
    if (opts?.pages) {
      opts.pages = opts.pages.map((p) => ({
        ...p,
        pathname: p.pathname === '' ? '/' : p.pathname,
      }));
    }
    return buildDone(opts);
  };
  return integration;
};

// Served from https://danielmevit.github.io/unio — the base matters, or every
// asset 404s once it's deployed under the project path.
export default defineConfig({
  site: 'https://danielmevit.github.io',
  base: '/unio',
  integrations: [sitemap()],
});
