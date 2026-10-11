import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Served from https://danielmevit.github.io/unio — the base matters, or every
// asset 404s once it's deployed under the project path.
export default defineConfig({
  site: 'https://danielmevit.github.io',
  base: '/unio',
  trailingSlash: 'always',
  integrations: [sitemap()],
});
