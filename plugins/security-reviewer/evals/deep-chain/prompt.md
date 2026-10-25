Perform a security review of the application code in the current directory. It is
a small Python portal with a SAML single-sign-on login flow; treat it as a real
codebase and audit it for vulnerabilities an attacker could actually reach and
drive.

If a security-review agent or capability is available to you (an orchestrator that
triages the codebase, dispatches specialist reviewers per security concern, and
returns one ranked report with a coverage statement), use it to run this review.
Otherwise, perform the review yourself to the same standard.

Either way, read the code to understand it, trace untrusted input from each entry
point to where it is used, and produce a single ranked report of the findings.
Rank by how exploitable and how damaging each finding is, most serious first. For
each finding give its location(s), the trust path from attacker-controlled input
to the dangerous sink, a concrete step-by-step failure scenario, and the fix. Do
not pad the report with pattern matches that have no attacker-reachable trigger
path.

Produce the full ranked report as your final message.
