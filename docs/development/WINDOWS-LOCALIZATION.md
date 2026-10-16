# Windows app language support

Owner-requested milestone, 2026-10-16T01:49:56+02:00. Planned capability; the native Windows app
and these translations are not implemented or shipped yet.

## Outcome

Use Unio in a preferred language without changing its task, command or review
semantics. Localize the shared interface that the Windows desktop app will
host, rather than build a second dashboard. Keep Windows ahead of macOS.

Offer a visible language selector during onboarding and in Settings. Detect
the Windows display language as an initial suggestion, allow an explicit
choice, and retain that choice across restarts and upgrades. Fall back to
English per missing key; an incomplete translation must not prevent startup.
Locale selection belongs to local user preferences, not a project's task files
or another user's paired session.

## Target languages

The owner requested major languages, Balkan languages, Czech and Slovak.
This initial target list is a plan, not a list of verified translations. Add
catalogs in manageable groups and publish only the languages actually checked.

| Group | Languages and catalog identifiers |
| --- | --- |
| First verification set | English `en`, Bulgarian `bg`, Czech `cs`, Slovak `sk` |
| Major European languages | German `de`, Spanish `es`, French `fr`, Italian `it`, Portuguese `pt-PT` and Brazilian Portuguese `pt-BR`, Dutch `nl`, Polish `pl`, Hungarian `hu`, Ukrainian `uk`, Russian `ru` |
| Remaining Balkan coverage | Albanian `sq`, Bosnian `bs`, Croatian `hr`, Greek `el`, Macedonian `mk`, Romanian `ro`, Slovenian `sl`, Turkish `tr`, Serbian Latin `sr-Latn`; Bulgarian is in the first set |
| Wider international coverage | Arabic `ar`, Hindi `hi`, Simplified Chinese `zh-Hans`, Traditional Chinese `zh-Hant`, Japanese `ja`, Korean `ko` |

Keep Czech and Slovak separate, and Slovak `sk` distinct from Slovenian `sl`.
Likewise, give Balkan languages their own labels and catalogs rather than silently
substituting another language. Validate identifier handling in the selected
runtime; missing formatting data must have a documented fallback rather than
invent support.

## What is translated

- Onboarding, project selection, agent setup explanations and subscription hints.
- Navigation, menus, Settings, buttons, empty states and accessibility labels.
- Human-facing task states, limit explanations, stop reasons and recovery guidance.
- Confirmation text, permission explanations and normal application errors.
- Windows shell resources and Store listing text for the languages actually released.

Keep CLI commands, flags, JSON fields, stable state/outcome codes, file paths,
model identifiers, task identifiers and copyable commands unchanged. Worker
output, owner task text and source code retain their original language. A localized
explanation can accompany an original diagnostic; it must not rewrite evidence
or imply that untranslated provider output was understood automatically.

## Implementation approach

1. Audit the shared interface for visible strings and establish a small glossary
   for task, worker, lead, review, save, allowance and Unknown. Extract stable
   message keys into local UTF-8 catalogs. Reuse the current interface and build;
   do not add a second orchestrator or a large dependency merely for translation.
2. Add one catalog loader, supported-locale metadata, a per-key English fallback
   and a persisted user choice. Use locale-aware dates, numbers and plural rules
   while preserving machine data. Bound and escape substituted text; translation
   catalogs must never supply executable HTML, commands or permissions.
3. Support text expansion, keyboard access and screen readers. Add direction-aware
   layout for Arabic and test right-to-left text alongside left-to-right paths,
   commands and model names. Keep pan/zoom and task ordering semantics consistent.
4. Preserve the brand font where it covers the script. Audit actual glyph coverage
   and use an accessible fallback for unsupported scripts; no missing-glyph boxes
   or forced Latin transliteration. Check Cyrillic, Greek, Arabic, Devanagari and CJK.
5. Translate and review one group at a time with capable AI workers, a shared
   glossary and independent linguistic review where available. Track draft,
   checked and published catalogs separately; generated text is not proof of
   native-language quality. No paid translation service is required by this plan.
6. Include catalogs in offline installation, upgrade and uninstall checks.
   Localize Store metadata only for languages with usable released UI coverage.
   Recheck Store packaging requirements during the Windows packaging milestone.

## Acceptance

Check missing keys and placeholders, plural forms, persisted selection, OS
language matching and English fallback. Include a deliberately expanded test
locale to find clipping. Exercise narrow windows, keyboard navigation and screen
reader labels. Check Arabic direction and mixed-script commands, Serbian Latin, Czech/Slovak distinctions and representative non-Latin glyphs.

Switching languages must preserve selected project/session, task identity,
Source/review evidence, account policy and copied command bytes. Verify offline
startup and upgrades. Distinguish a catalog coverage check from a linguistic
review; record languages with unverified wording honestly.

## Scope and estimates

Begin extraction when the shared desktop shell is ready so later screens do
not hard-code new English strings. Initial catalog/selector/fallback groundwork:
roughly 4–8 hours. First regional group with layout and focused checks: roughly
1–2 working days, plus independent language review. Remaining groups ship in
stages; re-estimate from the actual string inventory and reviewer availability.
These are additional localization estimates, not the native Windows runtime
or Microsoft Store certification estimate.

Keep the frozen 0.5.19 recovery release unchanged. Complete the four field fixes
before automatic delegation; localization belongs to the Windows app track.

Related plans: [Windows and desktop delivery](RELEASE-OUTLOOK-0.5.19-0.5.24.md),
[cross-platform stages](CROSS-PLATFORM.md), [brand rules](../BRAND.md) and
[main roadmap](ROADMAP.md).
