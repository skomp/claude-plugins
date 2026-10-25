# Security-reviewer plugin — design

**Date:** 2026-10-24
**Status:** design, awaiting approval
**Repository:** `skomp/claude-plugins`

## Resolutions after the builder check (2026-10-24)

A fresh builder reviewed this design and raised three questions. All three are
now settled; the resolutions are folded into the sections below and summarized
here so the decisions are legible:

1. **Can an invoked agent dispatch its own specialist subagents? (was blocking.)**
   Verified against the Claude Code docs (`sub-agents`, `plugins/components`,
   fetched 2026-10-24). **Yes** — a subagent may spawn subagents up to three
   layers below the main conversation (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`,
   default 3), provided its `tools` list includes `Agent`. So the orchestrator can
   run as a subagent the user invokes on demand — which is what the author asked
   for ("an agent, so it comes with an empty context") — and still dispatch the
   roster. **One unconfirmed point:** dispatching *named sibling plugin agents*
   (`<plugin>:<name>` as `subagent_type`) is documented only for a main-thread
   agent; from inside a subagent it is plausible but not stated. **Decision:** the
   orchestrator is a subagent (architecture B below). A spike is the first plan
   step: confirm a subagent can dispatch a scoped sibling agent by name; if it
   cannot, fall back to dispatching `general-purpose` subagents carrying
   orchestrator-composed role briefs. The author's roster + escape-hatch choice is
   preserved either way — only the dispatch mechanism differs. The main-thread
   route (plugin `settings.json "agent"`) is the documented fallback of last
   resort, rejected as default because it would consume the whole session instead
   of being invokable on demand.
2. **Is a behavioral eval in scope this cycle?** **Yes** — author decision. A
   seeded-vulnerability fixture the reviewer must find the chain in, with pass
   criteria for *found the real chain* and *suppressed the generic noise*, wired as
   a `claude plugin eval` suite. See "Verification" below.
3. **How rigid is the specialist→orchestrator report contract?** Settled (builder's
   call): a **structured markdown finding template** with stable fields, so dedupe
   and ranking are mechanical rather than prose reconciliation. See "The report
   contract" below.

## Intent and the why

The author wants an agent that does *proper* security reviews of the code and
architecture of a software system — not a linter pass, not a list of generic
"missing input validation" warnings. The defining win is the opposite of noise:
a deep, multi-step finding that needs special state and a particular sequence of
actions to trigger, the kind a pattern-matcher never sees. The live motivating
case is the author's own SAML identity provider, which they are hardening.

Two forces shape the whole design:

1. **Empty context is the point.** The author explicitly wants a reviewer that
   starts cold, with nothing in its context but the task, so no accumulated
   conversation bloats or biases its judgment. That is why this is an *agent*,
   invoked fresh, rather than a skill loaded into whatever session is running.

2. **Depth beats breadth, and depth needs isolation.** One context reviewing an
   entire system reviews everything shallowly. The design instead triages the
   system, then dispatches a focused specialist subagent per security concern it
   finds — each with its own clean context and a narrow brief — so each concern
   is reviewed deeply and in isolation.

## Goals

- Find real, exploitable vulnerabilities in a codebase's code *and* its
  architecture — especially multi-step chains that require specific state and
  actions to trigger.
- Review deeply per concern: one specialist context per security-sensitive area,
  not one context spread thin over the whole system.
- For each real finding, deliver three things:
  - a **written failure scenario** — the exact conditions, state, and sequence of
    actions that trigger the vulnerability, concrete enough to verify by reading
    and for any downstream agent to turn into a failing test;
  - a **plain explanation** of the vulnerability and why it works;
  - a **fix-and-harden proposal** — how to fix the specific bug, and how to harden
    the surrounding system against the class of bug.
- Be reusable across any codebase and any language, installed from this
  marketplace like the other six plugins.

## Non-goals

- **No proof-of-concept exploit, and no exploit code of any kind.** Dropped
  deliberately: the author is concerned a runnable PoC against third-party-hosted
  systems could run against GitHub's acceptable-use policy. The written failure
  scenario is the evidence of exploitability; it is not weaponized.
- **No failing test written by the reviewer.** Any downstream agent can write one
  from the failure scenario, so the reviewer stops at the report.
- **Not a generic noise generator.** A long list of low-confidence, context-free
  warnings is an explicit failure mode, not an acceptable fallback. The reviewer
  ranks by real exploitability and discards the generic noise.

## Anti-goals (what makes this a failure even if it technically runs)

- It returns a wall of generic findings and buries (or misses) the one real
  multi-step bug.
- It reviews the whole system in one bloated context and so reviews nothing
  deeply — the exact thing the empty-context, per-concern-subagent design exists
  to prevent.
- It fabricates a finding, or asserts exploitability it cannot substantiate with
  a concrete failure scenario. (The repo's `evidence-discipline` principle —
  never report a property until the opposite has been shown detectable — applies
  to findings here: a claimed vulnerability needs a concrete trigger path, and a
  "clean" verdict needs to say what was actually examined.)

## Scope of use

Authorized review of code the author controls or has permission to review. The
SAML provider is the first real target. The plugin is general-purpose across
codebases and languages; it carries no assumption that the target is the author's.

## How it works

### Shape: orchestrator + fixed roster + escape hatch

The author chose, explicitly, the third of three options: **a fixed roster of
specialist reviewer briefs, plus an escape hatch** for anything unusual the roster
does not cover — over a purely open-ended "invent the specialist on the fly"
approach (flexible but unpredictable) and over a closed fixed roster with no
escape hatch (repeatable but blind to the unusual).

So there are two kinds of agent:

- **The orchestrator** (the agent the user invokes). It starts cold. It does not
  itself hunt line-by-line for bugs; it **triages and dispatches**.
- **Specialist reviewers** (subagents the orchestrator dispatches). Each gets a
  clean context and a narrow brief: review *one* concern in *these* files, report
  back findings with failure scenarios.

**Architecture B — orchestrator as an invoked subagent.** The orchestrator is a
plugin agent (`agents/<name>.md`) the user dispatches on demand from any session,
so it starts with an empty context (the author's core requirement) and the user's
working session is untouched. Its `tools` frontmatter includes `Agent` so it can
dispatch; it runs one layer below the main conversation, and its specialists run a
second layer, well within the depth-3 limit. Dispatch of the fixed roster is by
scoped sibling name (`<plugin>:<concern>`) *if the step-one spike confirms a
subagent may do so*; otherwise by dispatching `general-purpose` subagents carrying
orchestrator-composed role briefs (one brief per concern). Either way the roster
and escape hatch behave identically — only the addressing differs.

### Step 1 — Triage (orchestrator)

The orchestrator maps the target before dispatching anything:

- Identify entry points and trust boundaries: where untrusted input enters (HTTP
  handlers, message consumers, file/upload parsing, CLI args, env, deserialization
  points), what is privileged, where the boundaries between them are.
- Detect which security-sensitive patterns are actually present in this codebase
  (raw SQL, crypto usage, auth/session handling, SAML/OIDC assertion parsing,
  external HTTP calls, path handling, secret/config loading, …).
- Produce a triage map: for each present concern, which specialist brief covers it
  and which files/regions it should look at.

The triage map is written down (as a working artifact) before dispatch, so the run
is inspectable and the orchestrator's coverage is legible.

### Step 2 — Dispatch specialists (fixed roster + escape hatch)

For each concern the triage found, the orchestrator dispatches the matching
specialist subagent with a scoped brief (the concern, the files, the trust
boundaries that reach it). Proposed fixed roster — each is one agent brief:

- **Injection** — SQL/NoSQL, command, LDAP, template, and other
  interpreter-boundary injection; raw query construction.
- **Cryptography** — algorithm and mode choice, key handling, randomness, signature
  and MAC verification, nonce/IV reuse, padding, constant-time comparison.
- **Authn / authz** — authentication and session handling, access control,
  privilege boundaries, and **SAML/OIDC/token** assertion parsing and validation
  (signature wrapping, audience/recipient/notOnOrAfter checks, replay). This is the
  concern the live SAML case lands in.
- **Untrusted deserialization & parsing** — object deserialization, XML (XXE,
  entity expansion, XSLT), and other parser-driven code-execution/exfiltration
  surfaces.
- **SSRF & outbound requests** — server-side request forgery, URL/host validation,
  redirect following, metadata-endpoint exposure.
- **Path & file handling** — path traversal, symlink handling, unsafe temp files,
  archive extraction ("zip slip").
- **Secrets & configuration** — hardcoded secrets, secret logging, unsafe defaults,
  permissive CORS/cookies/TLS settings, debug surfaces left on.

**Escape hatch:** when triage finds a security-sensitive pattern no roster brief
covers (an unusual protocol, a bespoke sandbox, a novel trust boundary), the
orchestrator dispatches a general security-reviewer subagent with a brief it writes
for that specific concern, following the same report contract as the fixed roster.

Specialists run with clean contexts and can run in parallel where the repo's
`parallel-sessions` rules allow (read-only review is safe to parallelize; the
reviewer writes no product files).

### Step 3 — Consolidate (orchestrator)

Specialists report back. The orchestrator:

- **dedupes** findings that several specialists reported (one SSRF seen by both the
  SSRF and the SAML-metadata reviewer is one finding);
- **ranks by real exploitability** — a triggerable multi-step chain outranks a
  theoretical weakness; generic, context-free observations are dropped rather than
  padded into the report;
- assembles the final report.

### Step 4 — Report

One report. For each real finding, the three deliverables above (failure scenario,
explanation, fix-and-harden proposal), ordered most-exploitable first. The report
also states what was examined and what was *not* reached (coverage), so a "nothing
critical found" verdict is honest about its scope rather than silently empty.

### The report contract

Specialists do not return free prose; the orchestrator can only dedupe and rank
mechanically if findings are comparable. Each specialist returns zero or more
findings in a **structured markdown template** with stable fields:

- **concern** — which roster brief (or escape-hatch brief) produced it;
- **title** — one line;
- **locations** — file paths and line ranges;
- **trust path** — which entry point / trust boundary reaches the flaw;
- **severity** and **exploitability** — ranked for the "real chain beats theoretical
  weakness" ordering; a finding with no concrete trigger path is marked as such and
  is a candidate for the orchestrator to drop as noise;
- **failure scenario** — the exact state and sequence of actions that trigger it;
- **explanation** — why it works;
- **fix-and-harden** — the specific fix plus the class-level hardening.

The orchestrator keys dedupe on (locations ∩ trust path), merges the merged
finding's fields, and ranks by exploitability then severity. The escape-hatch
subagent returns the identical template. The template is defined once and
referenced by every specialist brief, so the roster stays individually testable.

## The parts left to the builder

These are implementation decisions a competent builder can settle; defaults given
where there is an obvious one.

- **Plugin name.** Working name `security-reviewer`. The repo's other plugins have
  evocative one-word names (`machines`, `session-relay`). A better name is welcome;
  must not collide with the built-in `security-review` skill or `/code-review`
  command. *(Author decision if they have a preference; otherwise builder's call.)*
- **Exact agent file layout.** Follow `ticket-craft/agents/ticket-writer.md`:
  `agents/<name>.md` with `name`/`description`/`tools`/`model` frontmatter and a
  prose brief. The orchestrator needs `Agent` in its tools (it dispatches); the
  specialists are read-only (`Read`, `Grep`/`Glob`, `Bash` for read-only
  inspection). Separate `agents/*.md` files for the fixed roster (legible,
  individually testable) and a composed brief for the escape hatch — *conditional
  on the step-one spike* confirming a subagent can dispatch scoped sibling agents;
  if not, all concerns become composed briefs over `general-purpose` subagents (see
  the architecture-B resolution above). The template of "The report contract" is
  shared by every brief.
- **Model choice.** `ticket-writer` uses `haiku` for a mechanical task. Security
  review is judgment-heavy; default the orchestrator and specialists to the
  session's strong model rather than pinning `haiku`. Builder's call on exact ids.
- **How the user invokes it.** Via the Agent tool / agent type, matching how
  agents are surfaced in this marketplace. No slash command unless the builder
  finds one is the idiomatic entry point here.
- **Report destination.** Default: the report is returned to the invoking session
  as the agent's result (and the triage map + report may be written under a
  scratch/working path). Whether findings optionally become GitHub issues via
  `ticket-craft` is a follow-up, not part of this cycle.
- **Manifest plumbing.** New plugin dir under `plugins/`, `.claude-plugin/plugin.json`,
  a marketplace entry in `.claude-plugin/marketplace.json` (name ≠ `claude-plugins`),
  `README.md` written redacted per the repo rule, then `scripts/sync-manifests.py`
  run to regenerate the Codex/Copilot manifests. `CLAUDE_ONLY` need not list it
  (it is not Claude-only the way `tone-roulette` is — but confirm during build).
  `claude plugin validate .` before commit.

## Verification (in scope this cycle)

Structural validation (`claude plugin validate`, `sync-manifests.py --check`) proves
the manifests are well-formed but says nothing about whether the reviewer finds real
bugs — and the plugin's whole point is behavioral. So this cycle also ships a
**behavioral eval**:

- **A seeded-vulnerability fixture** — a small, deliberately-vulnerable codebase
  carrying at least one deep, multi-step chain (the kind needing specific state and
  a sequence of actions to trigger) plus benign code that invites generic false
  positives. Built in-repo as a test fixture (the author's real SAML provider lives
  outside this repo and is not the eval target). The SAML/assertion concern should
  be represented, since it is the live motivating case.
- **Pass criteria**, both required:
  - **found the real chain** — the ranked report names the seeded multi-step
    vulnerability with a correct, concrete failure scenario;
  - **suppressed the noise** — the report does not drown that finding in generic,
    context-free observations (a bound on low-value findings, exact threshold a
    builder's call).
- **Wired as a `claude plugin eval` suite**, so it runs like the repo's other
  checks. Follows the `evidence-discipline` principle: the eval must be shown to
  *fail* on a reviewer that misses the chain or floods noise, not only to pass —
  a check that has only ever passed is not evidence.

Because the fixture is a deliberately-vulnerable artifact, it is clearly labelled as
a test fixture and never presented as production code; it contains no working
exploit, only the vulnerable code and the seeded flaw.

## Constraints (from the repo)

- The plugin ships from `skomp/claude-plugins`; marketplace `name` stays
  `skomp-plugins`.
- Generated manifests (`.agents/…`, `.github/plugin/…`, `.codex-plugin/…`) are
  written by `scripts/sync-manifests.py`, never by hand; CI runs `--check`.
- README and any shipped text written redacted from the start if it draws on real
  cases: project names generic, dates/commands/errors/versions verbatim.
- Bump versions in both `plugin.json` and the marketplace entry on any change.
