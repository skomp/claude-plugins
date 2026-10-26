# security-reviewer

An orchestrator agent that reviews a codebase for security flaws and returns one ranked
report. It reads code and reports. It does not edit anything.

## What it is

You invoke the `security-review` agent. It starts with an empty context, so it knows
nothing about the target until it looks. It works in four steps:

1. **Triage.** It maps the entry points and trust boundaries of the codebase: where
   untrusted input arrives, and what that input can reach.
2. **Dispatch.** It sends one specialist reviewer per security concern that the triage
   shows is relevant. The roster is fixed, with an escape hatch for what the roster misses.
3. **Consolidate.** It removes duplicates, links findings that form one attack chain, and
   drops pattern-match noise that has no trust path to a real sink.
4. **Report.** It returns one ranked report with an explicit coverage statement: what was
   reviewed, and what was not.

Ask for it in plain words: "security review of this codebase", "audit this for
vulnerabilities", "is this system secure".

## The roster

| Concern | What the specialist looks at |
|---|---|
| **injection** | SQL, command, template, LDAP, XML and header injection |
| **crypto** | Weak or misused primitives, bad randomness, broken key handling |
| **authn** | Authentication and authorization, including SAML, OIDC and JWT validation |
| **deserialization** | Untrusted data fed to object deserializers |
| **ssrf** | Server-side requests built from attacker-controlled input |
| **paths** | Path traversal, unsafe file access, upload handling |
| **secrets** | Hard-coded secrets, unsafe configuration, leaked credentials |
| **general** | The escape hatch: a flaw that fits none of the above |

The briefs are in `reviewers/`. `reviewers/REPORT-CONTRACT.md` defines the report format.

## The report contract

Every real finding carries the same nine fields, in this order: **concern**, **title**,
**locations**, **trust path**, **severity**, **exploitability**, **failure scenario**,
**explanation**, **fix-and-harden**. Every specialist emits them and the orchestrator
consolidates on them. A candidate with no trust path from an untrusted source to a
dangerous sink is not a finding and does not reach the report.

## Boundary

This plugin produces a written failure scenario, an explanation, and a fix and hardening
proposal for each finding. It does **not** produce a proof-of-concept exploit, and it
writes no exploit code. Use it for authorized review of code you control or may review.

## Install

```
/plugin install security-reviewer --marketplace skomp/claude-plugins
```

## Run the eval

The bundled suite seeds one deep, multi-step flaw into a small fixture: a SAML identity
provider integration where the signature is verified over a different element than the
one the code consumes (XML signature wrapping). The reviewer passes if it finds that chain
and does not bury it in generic noise.

```
claude plugin eval plugins/security-reviewer --case deep-chain --trust-plugin --scaffold --runs 1 --judge-model sonnet
```

- Use `--judge-model sonnet`. The default haiku judge is noisy on long multi-finding
  reports and has produced a false negative.
- The suite needs `--scaffold`: `scaffold.sh` copies the fixture into the run.
- Do not grant `Bash` in the eval sandbox. Read, Glob, Grep and Agent cover the review,
  and a granted shell hard-fails where there is no OS sandbox backend.

## Known limitation

The eval shows that the reviewer finds the seeded multi-step chain, that it suppresses
generic noise, and that its grader fails a report that misses the chain. It does not yet
show the plugin's advantage over one capable single-agent review. That edge needs a larger
codebase than the small fixture. A larger fixture is a known follow-up.
