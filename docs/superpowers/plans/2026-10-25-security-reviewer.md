# Security-reviewer Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a seventh plugin in `skomp/claude-plugins` whose entry point is an orchestrator agent that triages a target, dispatches one specialist subagent per security concern, and returns one ranked report of real, exploitable findings.

**Architecture:** The orchestrator is a plugin agent (`agents/*.md`) invoked as a subagent, so it starts with an empty context. It triages entry points and trust boundaries, dispatches a fixed roster of specialist reviewer subagents (plus an escape hatch) that each review one concern in isolation and return findings on a shared structured template, then it dedupes and ranks into one report. A seeded-vulnerability fixture and a `claude plugin eval` suite prove the reviewer finds the deep chain and suppresses generic noise.

**Tech Stack:** Markdown agent definitions (Claude Code plugin agents); JSON manifests; `scripts/sync-manifests.py` (Python 3) for the Codex/Copilot manifests; `claude plugin validate` and `claude plugin eval` for checks; the fixture in whatever language reads clearest for the seeded flaw (default Python).

**Spec:** `docs/superpowers/specs/2026-10-24-security-reviewer-design.md`

## Global Constraints

- Plugin directory: `plugins/security-reviewer/` (working name; the author may rename — if so, rename consistently across dir, `plugin.json`, marketplace entry, agent scoped names, and this plan's paths).
- Marketplace `name` stays `skomp-plugins`; never `claude-plugins` (Claude Code rejects it).
- The plugin must NOT be added to `CLAUDE_ONLY` in `scripts/sync-manifests.py` — it is not Claude-only the way `tone-roulette` is (no output styles/hooks); it ships to Codex and Copilot too. Confirm by reading the script header.
- Generated files (`.agents/plugins/marketplace.json`, `.github/plugin/marketplace.json`, `plugins/*/.codex-plugin/plugin.json`) are written only by `scripts/sync-manifests.py`; never edit by hand. `scripts/sync-manifests.py --check` must pass before commit.
- `plugin.json` `version` and the marketplace entry `version` must match (sync script exits non-zero otherwise); start at `0.1.0`.
- Run `claude plugin validate .` before committing any manifest or `plugin.json` change.
- Agents default to the invoking session's model (omit the `model` frontmatter key — do NOT pin `haiku`; security review is judgment-heavy). Orchestrator's `tools` must include `Agent` (it dispatches); specialists are read-only: `Read, Grep, Glob, Bash`.
- Deliverables are prose agent briefs: they are verified structurally (`claude plugin validate`) and behaviorally (the eval), not by unit tests. Only the fixture, graders, and sync/validate checks are mechanically testable.
- No proof-of-concept exploit and no exploit code anywhere, including the fixture (the fixture holds vulnerable code and the seeded flaw, never a weaponized exploit). The fixture is labelled a test fixture, never presented as production code.
- Redaction: this plugin is net-new (not distilled from a redacted source project), so content is original; keep the SAML example generic ("a SAML identity provider"), name no real project, author handle, or private host. Prove it with a grep before commit (Task 5), planting a token first per the repo rule.
- Session-URL rule: never put a `claude.ai/code/session_*` URL in any committed file, commit message, PR, or issue body.

## Review Focus

The spec implies inputs no single structural check exercises; each is pinned to a task below.

- **A target with zero findings** — the orchestrator must emit an honest "examined X, did not reach Y, nothing critical found" report, not a silently empty one or an invented finding. → Task 2 (orchestrator brief + eval clean-arm in Task 4).
- **Generic-noise flood** — benign code that invites low-value observations must not drown the real finding; the orchestrator drops no-trigger-path findings. → Task 2 (consolidation) + Task 4 (the "suppressed the noise" grader).
- **A concern with no matching roster brief** — an unusual trust boundary must route to the escape hatch, not be dropped. → Task 3 (escape-hatch brief).
- **Depth-limit / dispatch failure** — if a subagent cannot dispatch a scoped sibling by name, the orchestrator must fall back to composed briefs over `general-purpose` rather than fail silently. → Task 1 (spike decides) + Task 2 (orchestrator brief states the fallback).
- **A huge target** — triage must scope specialists to regions, not hand each the whole tree; an unbounded review is the "bloated context" failure the design exists to prevent. → Task 2 (triage step writes a scoped map).

---

## Task 1: Spike the dispatch path, then scaffold the plugin skeleton

**Files:**
- Create: `plugins/security-reviewer/.claude-plugin/plugin.json`
- Create: `plugins/security-reviewer/README.md` (stub; full README in Task 5)
- Create: `plugins/security-reviewer/agents/.gitkeep` (placeholder until Task 2/3)
- Modify: `.claude-plugin/marketplace.json` (add the entry)
- Generated (via script, do not hand-edit): `.agents/plugins/marketplace.json`, `.github/plugin/marketplace.json`, `plugins/security-reviewer/.codex-plugin/plugin.json`

**Interfaces:**
- Produces: the plugin name `security-reviewer`, version `0.1.0`, and the decided dispatch mechanism (named sibling vs composed-brief) that Tasks 2 and 3 consume.

- [ ] **Step 1: Spike — can a subagent dispatch a scoped sibling plugin agent by name?** Create a throwaway plugin with an orchestrator agent (`tools: Agent`) and two trivial worker agents, install/point at it, invoke the orchestrator as a subagent, and have it call the Agent tool with `subagent_type` set to a scoped worker name (`<plugin>:<worker>`). Record whether the named dispatch succeeds and whether fork mode (`CLAUDE_CODE_FORK_SUBAGENT`) affects awaiting results.
- [ ] **Step 2: Record the spike outcome.** If named sibling dispatch works → roster specialists become separate `agents/*.md` files (Task 3). If it does not → all specialists become orchestrator-composed role briefs dispatched to `general-purpose`. Write the verdict and the evidence into the design doc's resolution section (append a dated note) so Tasks 2–3 read one source of truth. Delete the throwaway spike plugin.
- [ ] **Step 3: Write `plugin.json`.** Mirror `plugins/ticket-craft/.claude-plugin/plugin.json`: keys `name` (`security-reviewer`), `version` (`0.1.0`), `description` (one line), `author` (`{ "name": "skomp", "url": "https://github.com/skomp" }`), `homepage`, `repository`, `license` (`MIT`), `keywords` (e.g. `["security", "review", "audit", "vulnerability", "agent"]`).
- [ ] **Step 4: Add the marketplace entry** to `.claude-plugin/marketplace.json` `plugins` array: `name`, `source` (`./plugins/security-reviewer`), `version` (`0.1.0`), `category` (`development`), `description`, `author`. Keep `version` identical to `plugin.json`.
- [ ] **Step 5: Write a stub `README.md`** (one paragraph; full version in Task 5) so the plugin dir is coherent.
- [ ] **Step 6: Run the sync script.** Run: `scripts/sync-manifests.py`. Expected: writes the three generated files for `security-reviewer`; no error about a version mismatch.
- [ ] **Step 7: Validate and check.** Run: `claude plugin validate .` → expected: passes. Run: `scripts/sync-manifests.py --check` → expected: exit 0 (nothing stale).
- [ ] **Step 8: Commit.**
```bash
git add plugins/security-reviewer .claude-plugin/marketplace.json .agents/plugins/marketplace.json .github/plugin/marketplace.json docs/superpowers/specs/2026-10-24-security-reviewer-design.md
git commit -m "security-reviewer: scaffold plugin and record dispatch spike"
```

## Task 2: Report contract and the orchestrator agent

**Files:**
- Create: `plugins/security-reviewer/agents/REPORT-CONTRACT.md` (the shared finding template, referenced by every brief)
- Create: `plugins/security-reviewer/agents/security-review.md` (the orchestrator; invoked as `security-reviewer:security-review`)

**Interfaces:**
- Consumes: the dispatch verdict from Task 1.
- Produces: the orchestrator agent, and the finding-template fields that every specialist in Task 3 must emit: `concern`, `title`, `locations`, `trust path`, `severity`, `exploitability`, `failure scenario`, `explanation`, `fix-and-harden`.

- [ ] **Step 1: Write `REPORT-CONTRACT.md`.** Define the structured-markdown finding template with exactly the nine fields above, each with a one-line definition and an example line, plus the rule: a finding with no concrete trigger path is marked `exploitability: none` and is a drop candidate. This file is the single definition the orchestrator and all specialists reference.
- [ ] **Step 2: Write the orchestrator brief `security-review.md`** with frontmatter `name: security-review`, a `description` that triggers on "security review / audit this codebase / review for vulnerabilities", `tools: Agent, Read, Grep, Glob, Bash`, and no `model` key. The body specifies the four steps from the spec: (1) **Triage** — map entry points, trust boundaries, and which security-sensitive patterns are present; write a scoped triage map (which concern, which files) before dispatching. (2) **Dispatch** — one specialist per present concern, scoped to its files; by named sibling or composed brief per Task 1's verdict; escape hatch for any concern no brief covers. (3) **Consolidate** — dedupe on (locations ∩ trust path), rank by exploitability then severity, drop no-trigger-path noise. (4) **Report** — ranked findings (failure scenario, explanation, fix-and-harden each), plus an explicit coverage statement (what was examined, what was not reached) so a clean verdict is honest.
- [ ] **Step 3: Validate.** Run: `claude plugin validate .` → expected: passes (agent frontmatter well-formed).
- [ ] **Step 4: Confirm the orchestrator loads.** Run: `claude plugin validate .` output lists the `security-review` agent, or `/agents`-equivalent listing resolves `security-reviewer:security-review`. Expected: present.
- [ ] **Step 5: Commit.**
```bash
git add plugins/security-reviewer/agents
git commit -m "security-reviewer: add report contract and orchestrator agent"
```

## Task 3: Specialist roster and escape hatch

**Files (if Task 1 chose named siblings):**
- Create: `plugins/security-reviewer/agents/review-injection.md`
- Create: `plugins/security-reviewer/agents/review-crypto.md`
- Create: `plugins/security-reviewer/agents/review-authn.md` (authn/authz incl. SAML/OIDC/token)
- Create: `plugins/security-reviewer/agents/review-deserialization.md`
- Create: `plugins/security-reviewer/agents/review-ssrf.md`
- Create: `plugins/security-reviewer/agents/review-paths.md`
- Create: `plugins/security-reviewer/agents/review-secrets.md`
- Create: `plugins/security-reviewer/agents/review-general.md` (escape hatch)

**(If Task 1 chose composed briefs:** these become brief sections the orchestrator composes, embedded in or beside `security-review.md`, not separate agent files. Same eight concerns, same template.)

**Interfaces:**
- Consumes: `REPORT-CONTRACT.md` (every brief references it and emits its nine fields); the dispatch verdict from Task 1.
- Produces: eight concern reviewers addressable by the orchestrator.

- [ ] **Step 1: Write each specialist brief.** Each has `tools: Read, Grep, Glob, Bash`, no `model` key, a `description` naming its concern, and a body that: states the concern's threat classes (from the spec's roster — e.g. injection covers SQL/NoSQL/command/LDAP/template; authn covers signature wrapping, audience/recipient/notOnOrAfter, replay; etc.), takes a scoped brief (concern + files + trust boundaries), reviews only that, and returns findings on the shared template. The escape-hatch brief (`review-general`) takes an orchestrator-written concern description for anything the roster does not cover and follows the identical template.
- [ ] **Step 2: Cross-check field names** against `REPORT-CONTRACT.md` — every brief emits the same nine fields with the same names the orchestrator dedupes/ranks on. A mismatch here silently breaks consolidation.
- [ ] **Step 3: Validate.** Run: `claude plugin validate .` → expected: passes; all roster agents resolve.
- [ ] **Step 4: Commit.**
```bash
git add plugins/security-reviewer/agents
git commit -m "security-reviewer: add specialist roster and escape hatch"
```

## Task 4: Seeded-vulnerability fixture and eval suite

**Files:**
- Create: `plugins/security-reviewer/evals/deep-chain/prompt.md` (the review task pointed at the fixture)
- Create: `plugins/security-reviewer/evals/deep-chain/graders/found-chain.md` (LLM grader: did the report name the seeded chain with a correct failure scenario?)
- Create: `plugins/security-reviewer/evals/deep-chain/graders/suppressed-noise.md` (grader: is the real finding not drowned — bound on low-value findings)
- Create: `plugins/security-reviewer/evals/deep-chain/fixture/` (the deliberately-vulnerable codebase, with a SAML/assertion concern represented)
- Create: `plugins/security-reviewer/evals/deep-chain/case.yaml` (if `case.yaml` form is used instead of bare `prompt.md` + graders)
- Modify: `plugins/security-reviewer/.claude-plugin/plugin.json` (add `experimental.evals` pointing at `evals/` only if the default `evals/` dir is not auto-discovered — confirm against `claude plugin eval --help`)

**Interfaces:**
- Consumes: the orchestrator and roster (Tasks 2–3).
- Produces: a runnable `claude plugin eval` suite and the fixture.

- [ ] **Step 1: Build the fixture.** A small codebase (default Python) with: at least one deep, multi-step vulnerability needing specific state + a sequence of actions to trigger (represent the SAML/assertion concern — e.g. an assertion-validation gap reachable only through a particular flow); plus benign code that invites generic false positives. Label the dir clearly as a test fixture. No exploit code — vulnerable code and the seeded flaw only.
- [ ] **Step 2: Write `prompt.md`** instructing a run to security-review the fixture dir and produce the ranked report.
- [ ] **Step 3: Write the two graders.** `found-chain.md`: pass iff the report names the seeded multi-step vulnerability with a concrete, correct failure scenario (LLM grader). `suppressed-noise.md`: pass iff the report keeps low-value/no-trigger findings under a stated bound (threshold is the builder's call; state it in the grader).
- [ ] **Step 4: Prove the eval FAILS when it should** (evidence-discipline). Run the suite with `--ablation with-without` so the no-plugin baseline arm runs; confirm the baseline (or a deliberately blinded run) scores below threshold on `found-chain`, i.e. the grader actually detects a miss. Run: `claude plugin eval plugins/security-reviewer --ablation with-without --scaffold --trust-plugin`. Expected: the without-plugin arm does not pass `found-chain`.
- [ ] **Step 5: Prove the eval PASSES with the plugin.** Same command; expected: the with-plugin arm passes both graders at threshold. Record scores.
- [ ] **Step 6: Commit.**
```bash
git add plugins/security-reviewer/evals plugins/security-reviewer/.claude-plugin/plugin.json
git commit -m "security-reviewer: add seeded-vuln fixture and eval suite"
```

## Task 5: README, docs, redaction proof, and finish

**Files:**
- Modify: `plugins/security-reviewer/README.md` (full version)
- Modify: `README.md` (repo root — add the plugin to the plugin list if the root README enumerates them)
- Modify: `plugins/security-reviewer/.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (no version bump needed on first ship; bump only on later change)

**Interfaces:**
- Consumes: everything above.
- Produces: a closeable branch.

- [ ] **Step 1: Write the full README** (redacted from the start): what the plugin is, the orchestrator + roster + escape-hatch shape, the report contract, how to invoke it, how to run the eval, and the "no PoC / no exploit code" boundary. Keep the SAML example generic.
- [ ] **Step 2: Add the plugin to the root `README.md`** if it lists the plugins (check first; match the existing entry style).
- [ ] **Step 3: Prove the redaction.** First plant a token in a scratch copy to prove the grep detects it, then run against the real tree. Run: `grep -rniE '<any-real-project-or-host-token>' plugins/security-reviewer/ && echo LEAK || echo clean`. Expected: `clean` on the real tree, `LEAK` on the planted scratch copy. Also grep for `session_` URLs: `grep -rn 'session_' plugins/security-reviewer/ docs/ && echo FOUND || echo clean`.
- [ ] **Step 4: Final sync + validate.** Run: `scripts/sync-manifests.py && scripts/sync-manifests.py --check` (expected: no stale files) and `claude plugin validate .` (expected: passes).
- [ ] **Step 5: Commit, push, open a draft PR.**
```bash
git add plugins/security-reviewer/README.md README.md .agents .github/plugin
git commit -m "security-reviewer: full README and repo plugin list"
git push -u origin security-reviewer-plugin
gh pr create --draft --title "Add a security-reviewer agent plugin" --body-file <(printf '...')
```
PR body states what the eval proved, the dispatch verdict from Task 1, and anything still unsure. Draft until the eval scores are in and the author has looked.

---

## Self-Review

**1. Spec coverage** — intent/why → Task 2 orchestrator. Empty-context agent → Task 1 spike + Task 2 (subagent invocation). Triage → Task 2 step 2. Fixed roster + escape hatch → Task 3. Consolidation (dedupe/rank/drop noise) → Task 2 + Report Focus. Three deliverables per finding → REPORT-CONTRACT (Task 2) + specialists (Task 3). Report contract → Task 2. Eval (seeded fixture, both pass criteria, `claude plugin eval`, shown to fail first) → Task 4. Manifest plumbing/constraints → Tasks 1 & 5. No PoC → Global Constraints + Task 4. Covered.

**2. Step scan** — prose-agent steps decide responsibility, tools, frontmatter, and the shared field set; they do not transcribe brief bodies (the model writes idiomatic prose from the responsibility). Testable steps carry exact commands and expected results. No "handle edge cases" lines.

**3. Type consistency** — the nine finding fields are defined once in Task 2 and referenced by name in Tasks 2, 3, and 4; Task 3 step 2 is an explicit cross-check against that definition.

**4. Review Focus** — five implied inputs listed, each pinned to an owning task (clean target, noise flood, no-matching-concern, dispatch failure, huge target).

**5. Proportion** — plan is comparable to the spec, not a transcript; the only code artifact is the fixture (Task 4), whose body is left to the implementer because the seeded flaw's exact shape is theirs to craft within the stated constraints.
