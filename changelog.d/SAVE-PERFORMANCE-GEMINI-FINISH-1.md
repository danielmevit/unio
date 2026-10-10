### Offline recovery-save performance probe

- Add a source-checkout utility for measuring the installed CLI in a fresh
  private local fixture, without provider calls or real-project changes.
- Record engine identity, filesystem, command timing, save attempts and
  manifest-confirmed IDs; preserve failures and Unknown observations.
- Bound Git and engine process groups, output and total execution; preserve
  HOME and isolate configuration. Cleanup requires an explicit option.
- Document the observed 0.5.9 disk baseline without claiming a speedup.

AI-Assisted-By: GLM 5.3 / Mistral Vibe (preserved partial), Gemini / Antigravity, Codex (lead correction)
