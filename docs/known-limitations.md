# Known limitations

- **The messages are synthetic, and one person wrote all of them.** The fresh phrasings were written after the
  freeze, but by the same author as the lexicon, so they probably share habits of wording. Real tenant messages
  (misspellings, several problems in one message, photos, other languages) would be the real test.
- **The validation phrasings are not a clean test.** They were looked at while the hazard lexicon was written (ADR 1).
  Their numbers are reported, but the fresh phrasings are the test.
- **Emergencies that use none of the lexicon's words are missed unless the model is sure.** On fresh phrasings this
  included "the ceiling has come down", "the socket went bang and is black" and "the window frame fell out".
- **One limit set in advance was missed:** night-time false alarms on the fresh phrasings (ADR 1).
- **Urgent versus routine is the weakest decision** (about 7 in 10 right on fresh phrasings). It only changes the
  order the inbox is read in, a few minutes, not whether someone is called at night.
- **The dispatch simulation is simple.** Contractors are always available, an emergency is attended 1 to 3 hours
  after dispatch, the inbox is read three times each weekday, and a call-back always finds the truth. Real capacity,
  travel and missed calls would change the numbers for every policy.
- **Claude's second reading is not measured** (ADR 3).
- **The ledger handles one currency, monthly rent and flat or percentage late fees.** No deposits, no utilities,
  no payment plans, no local rules on fee limits or notice periods.
- **The console is a demo:** one portfolio held in memory at a fixed time, with no logins and no editing.
