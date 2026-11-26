import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Served at https://unio.damt.xyz/ (GitHub Pages custom domain); the old
// danielmevit.github.io/unio/ address redirects here.
export default defineConfig({
  site: 'https://unio.damt.xyz',
  base: '/',
  trailingSlash: 'always',
  integrations: [sitemap()],
});
