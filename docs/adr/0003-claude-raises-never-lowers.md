# 3. Claude may raise a request's urgency, never lower it

## Context

A language model reads a tenant's message better than a lexicon does: it knows that "the ceiling is bulging and
dripping fast" means water is escaping, without anyone having listed "bulging". But it can also be wrong, and the
two kinds of error cost very different amounts. A false alarm costs the on-call coordinator a phone call. A missed
emergency costs a flooded flat, or worse.

## Decision

- The local triage (hazard screen and model, ADR 1) always runs and always decides first. It needs no network and
  no key, and it is what the evaluation measures.
- When an API key is set, Claude (`claude-opus-5-5`, low effort, with refusal fallbacks) reads the message too and
  fills a strict tool: urgency, trade, a one-line job description for the contractor, and the exact words that show
  the urgency.
- Code checks the answer: the urgency and trade must be known values and the quote must appear in the message.
  Then **Claude's reading can only raise the urgency**. If it says "emergency" with a valid quote and the local triage
  said "urgent", the request becomes an emergency and the quote is shown first among the reasons. If it says
  "routine" when the local triage said "emergency", the emergency stands and a note says Claude disagreed.
- A different trade from Claude is shown as a suggestion; it doesn't change the dispatch.
- The system prompt tells Claude to judge the problem, not the tone, and that text inside the request is never an
  instruction.
- A refusal, no tool call or a failed check leaves the local decision as it was.

## Consequences

- Claude can only add on-call calls, never remove one. The false-alarm rate can go up, and the emergency rate can't
  go down.
- **Claude's accuracy is not measured here.** The evaluation runs without a key, and measuring it would mean paid
  calls over thousands of messages. The tests check the request shape and the merge rules through the real SDK with
  canned responses.
- If Claude were measured and found reliable, the next step would be letting it *lower* urgency for messages where
  the local triage is unsure. That should only follow a measurement on fresh phrasings, like the one in ADR 1.
