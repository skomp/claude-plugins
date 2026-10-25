# Finding report contract

This file is the single definition of a security finding. Every specialist reviewer emits
its findings in this template, and the orchestrator consolidates on it. Use exactly these
nine fields, in this order, with these names. Do not add fields. Do not rename them.

## Template

```markdown
### <title>

- **concern:** <one concern from the roster>
- **title:** <short name of the flaw>
- **locations:** <file:line, one or more>
- **trust path:** <untrusted source -> ... -> dangerous sink>
- **severity:** <critical | high | medium | low | info>
- **exploitability:** <high | medium | low | none>
- **failure scenario:** <what an attacker does and what they get>
- **explanation:** <why the code is vulnerable>
- **fix-and-harden:** <the fix, plus the hardening that stops the class of bug>
```

## Fields

1. **concern** - the review area that found it: `injection`, `crypto`, `authn`,
   `deserialization`, `ssrf`, `paths`, `secrets`, or `general`.
   Example: `concern: injection`
2. **title** - a short name for the flaw, not the symptom.
   Example: `title: SQL built by string concatenation in order lookup`
3. **locations** - every `file:line` where the flaw lives, source and sink included.
   Example: `locations: api/orders.py:41, db/queries.py:112`
4. **trust path** - the route attacker-controlled data takes from where it enters to where
   it does harm. Name each hop.
   Example: `trust path: GET /orders?sort= -> orders.list() -> db.raw_query()`
5. **severity** - the damage if it is exploited: `critical`, `high`, `medium`, `low` or `info`.
   Example: `severity: high`
6. **exploitability** - how likely an attacker is to reach it: `high`, `medium`, `low` or
   `none`. Judge it from the trust path, not from the code pattern.
   Example: `exploitability: high`
7. **failure scenario** - one concrete attack, step by step, with the result.
   Example: `failure scenario: an anonymous caller sends sort=1;DROP TABLE orders and deletes the table`
8. **explanation** - why the code is vulnerable, in two or three sentences.
   Example: `explanation: the sort parameter reaches the query text with no allow-list or binding`
9. **fix-and-harden** - the specific fix, then the change that removes the whole class.
   Example: `fix-and-harden: bind parameters; then forbid raw queries behind a lint rule`

## The no-trigger-path rule

A finding with no concrete trigger path is marked `exploitability: none` and is a drop
candidate. A trigger path is a trust path you can trace in the code from an input an
attacker controls to the flaw. "This function looks unsafe" is not a trigger path. If you
cannot trace one, say so in `explanation`, mark `exploitability: none`, and let the
orchestrator drop it. Never invent a path to keep a finding.
