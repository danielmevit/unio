# Help people discover Unio in AI answers

Use this checklist to help assistants find, understand and cite Unio when
people ask relevant questions with web search enabled. There is no universal
registration for all AI assistants, and publishing a website does not instantly
update a model's built-in knowledge. Crawl access and indexing create an
opportunity to appear; they do not guarantee a recommendation.

Official guidance last checked: **2026-10-11**. Check items as you complete
them; this document does not submit the site or change account settings.

## 1. Publish and check the website

- [ ] Publish the SEO changes and confirm the GitHub Pages deployment succeeds.
- [ ] Open [Unio's homepage](https://danielmevit.github.io/unio/) in a browser
  without signing in. Confirm its description, features and installation links
  are readable.
- [ ] Open the [generated sitemap index](https://danielmevit.github.io/unio/sitemap-index.xml)
  and the sitemap it references. Both should return successfully after deployment.
- [ ] Confirm the sitemap lists real public pages using their canonical URLs.
  The homepage is `https://danielmevit.github.io/unio/`, including the final slash.
- [ ] Keep the Google verification file at
  `site/public/googlecb41a1d9722becfd.html` and confirm its deployed copy remains
  accessible at `/unio/googlecb41a1d9722becfd.html`.

Google accepts sitemap indexes and recommends absolute canonical URLs. Keeping
the HTML verification file published preserves that verification method.
[Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap),
[verification guidance](https://support.google.com/webmasters/answer/9008080).

## 2. Complete Google Search Console setup

- [ ] Open [Google Search Console](https://search.google.com/search-console)
  and select the verified property covering `https://danielmevit.github.io/unio/`.
- [ ] Under **Sitemaps**, submit this full URL and check that Google can process it:

```text
https://danielmevit.github.io/unio/sitemap-index.xml
```

- [ ] Inspect `https://danielmevit.github.io/unio/` with **URL Inspection**.
  Use the live test if needed, resolve any indexing restriction, and select
  **Request indexing**.
- [ ] Check **Settings → Search generative AI**. Choose **Include**, or confirm
  the property inherits inclusion. Google documents inclusion as the default.
- [ ] Monitor the sitemap status, page indexing and URL Inspection results.
  Repeated requests for the same unchanged URL do not accelerate crawling.

The inclusion setting covers Google Search's AI features, including AI Overviews
and AI Mode. It is separate from the Gemini app and model-training controls.
[Search AI control](https://support.google.com/webmasters/answer/16908024),
[requesting a recrawl](https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl).

## 3. Add Bing Webmaster Tools

- [ ] Sign in to [Bing Webmaster Tools](https://www.bing.com/webmasters/).
- [ ] Import the verified property from Search Console, granting the requested
  access if you choose that route; alternatively add and verify it manually.
- [ ] Confirm the generated sitemap index above is listed under **Sitemaps**;
  submit it if it was not imported.
- [ ] Use Bing's URL Inspection and sitemap status to investigate actual errors.

This supports discovery in Bing and Microsoft's AI search experiences, including
Copilot. It is useful alongside the assistants' own crawlers, and is not a
universal registration in ChatGPT, Claude or Gemini.
[Bing site verification](https://www.bing.com/webmasters/help/add-and-verify-site-12184f8b),
[Bing sitemap guidance](https://blogs.bing.com/webmaster/2025/7/Keeping-Content-Discoverable-with-Sitemaps-in-AI-Powered-Search/).

## 4. Keep the relevant crawlers able to reach public pages

- [ ] Check the effective host-level robots policy and any hosting access rules.
  Public pages should be reachable without a login or a challenge blocking
  legitimate crawlers. If access is already unrestricted, extra allow rules
  are unnecessary.
- [ ] Keep search access separate from decisions about model training:

| Experience | Relevant control | What it means |
| --- | --- | --- |
| ChatGPT search | `OAI-SearchBot` | Search discovery; `GPTBot` controls training separately. Allowing training is not required for search access. |
| Claude search | `Claude-SearchBot` | Search discovery; `Claude-User` handles user retrieval, while `ClaudeBot` is the separate training crawler. |
| Google Search and its AI features | `Googlebot` and Search Console's AI inclusion setting | Search crawl access plus eligibility for Google's generative search features. |
| Gemini answers grounded in web content | `Google-Extended` | Google says this controls both grounding in Gemini Apps and training future Gemini models. Choose with both uses in mind. |
| Perplexity search | `PerplexityBot` | Search discovery; Perplexity says this crawler is not used for foundation-model training. |

`Google-Extended` is a robots control token, not a separate HTTP crawler identity.
It does not determine inclusion or ranking in ordinary Google Search. The Gemini
and Google Search rows above describe different controls.
[Google crawler documentation](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers#google-extended).

Refer to each lab's current documentation before changing its rules:
[OpenAI crawlers](https://developers.openai.com/api/docs/bots),
[Anthropic crawlers](https://privacy.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler),
[Perplexity crawlers](https://docs.perplexity.ai/docs/resources/perplexity-crawlers).
Do not assume an HTTP request with a bot-like name proves an actual crawler visit.

### Important for this GitHub Pages address

The effective robots URL is `https://danielmevit.github.io/robots.txt`.
The project's `/unio/robots.txt` is below the host root and does not control
Google's crawling policy. A host-root 404 means no robots restrictions for
Google; it does not by itself prevent indexing.

If you later want an explicit host-wide policy or sitemap directive, publish it
through the root GitHub Pages site, or use a dedicated domain. Until then,
direct sitemap submission to Search Console and Bing is sufficient to tell
those services where the sitemap is. Recheck URLs if the site moves.
[Google robots location and HTTP handling](https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec).

## 5. Publish useful information people can find and cite

- [ ] Explain what Unio does in plain language: coordinate agents from different
  AI labs, delegate work, review changes independently, and preserve progress
  through handoffs while the owner stays in control.
- [ ] Publish working installation steps, a short real workflow, supported
  integrations and clear limitations. Distinguish shipped features from plans.
- [ ] Keep the project name, tagline, homepage URL and release information
  consistent between the website and [official repository](https://github.com/danielmevit/unio).
  Link the website and repository to each other.
- [ ] Give important documentation clear headings and crawlable links. When
  adding website pages, confirm they appear in the generated sitemap.
- [ ] Share useful releases and first-hand examples in relevant communities.
  Avoid fabricated reviews, repeated promotional posts or pages made only to
  target tiny variations of the same AI question.

These are ongoing content practices, not a special submission protocol.
Google recommends useful original content and ordinary technical SEO for its
AI search experiences. It says `llms.txt` is not used to improve visibility or
rankings in Google Search, including generative features. Such a file may help
other tools that explicitly support it, but is not a universal AI registration.
[Google's AI search guidance](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide).

## 6. Check progress without confusing access with discovery

- [ ] Check Search Console and Bing reports periodically, and after significant
  releases. Fix reported crawl or indexing problems before buying extra tools.
- [ ] In fresh chats with web search enabled, try both a named question and a
  natural category question, for example:
  - "What is Unio, the CLI for coordinating AI coding agents?"
  - "What tools can coordinate coding agents from different AI labs and review their work?"
- [ ] Record the date, assistant, exact question, cited URLs and whether the
  description was accurate. Compare the same questions over time; answers vary.
- [ ] Keep direct URL retrieval as a separate check. An assistant reading a link
  you supplied proves access, not that it would independently recommend Unio.

Search Console and Bing Webmaster Tools are the starting tools. An optional
self-hosted audit or analytics tool can track technical checks, visits or sampled
answers; it cannot register Unio in every assistant or force citations. Normal
browser requests and bot-name simulations also cannot prove that an AI lab has
crawled or indexed a page.

The goal is that a searching assistant can reach reliable public information,
understand when Unio fits the question, and cite the correct project.
