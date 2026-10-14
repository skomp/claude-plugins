---
name: completing-a-correction
description: "Use the moment a correction lands: you just fixed a defect or a bug; you just corrected a number, a measurement or a published claim; you just ruled that a review finding is valid; you are about to declare a fix done or write 'fixed' in a report or a dispatch; you are about to correct something you already told your human partner."
---

# Completing a Correction

## The One Rule

**A ruling is not complete when the code is fixed. It is complete when every artefact carrying the same claim is fixed** — spec, plan, README, CLAUDE.md, tests, dispatch prompts, and any comment restating the value.

## What it cost

A C and Python project, 2026-08-22. Three separate review rounds in one session, always the same way: you ruled on a defect, fixed **the instance in front of you**, and left identical copies elsewhere. Three different artefact types, which is the point:

- You ruled the log table's monotonicity assertion wrong (index 0 is a placeholder). You fixed the Python test. The **C test had the same assertion** — you shipped it, and an implementer caught it a task later.
- You corrected a wrong measurement in the spec's results table. You missed the same wrong figure in the spec's own **Decisions table** until you swept afterwards.
- You declared a JSON schema stale and corrected **the dispatch prompt** that consumed it. You never corrected **the plan document** it came from — so the plan still read "a contract, not a suggestion" above a stale schema with a figure that was wrong by 76 bytes, in the direction that implied the feature did nothing. The final whole-branch review called it "the single most damaging thing on the branch, because it reads as authoritative to the next session."

## The Mandatory Procedure

When you correct a fact or a defect:

1. `grep -rn` the corrected *number*, the *old* number, and a distinctive phrase from the wrong claim, across the whole repo including docs and plans. Do it **before** declaring the fix done, not after.
2. Fix every hit, and say in the dispatch or report how many instances you found. "Fixed 1 of 3" caught silently is the failure mode.
   - **Grep the old *referent* too, not only numbers and phrases.** When the correction changes *which thing* something points at — a filename, an asset, an identifier, a flag — the stale copies contain none of your numbers and none of your wording, so step 1 as written sails straight past them. A tutorial bundles project, 2026-09-29: a lesson's experiment was moved from `truncated.png` to `basic.png` because the first file cannot show the effect, the body was rewritten to explain exactly that, and the completion condition forty lines below still demanded the reading from `truncated.png`. The lesson ended up asking for a measurement it had just spent a paragraph proving was meaningless. Nothing was wrong with the new text; the miss was a second reference to the *old* referent inside the same file. So grep the old name as well as the old number — and grep the file you just edited, not only the rest of the repo.
3. For a fact that was published to your human partner, leave an explicit **correction note** rather than silently restating the new value — someone read the old one. Both the spec and the plan on that project carry one, and that was the right call.

## Why documents are worse than code

Code that contradicts itself usually fails a test. A document that contradicts itself just misleads the next reader with full authority.
