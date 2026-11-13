# Property management: evaluation

Maintenance requests written the way tenants write them, triaged by urgency and trade, then a simulated month per portfolio of who gets to an emergency how fast. Plus a year of rent through two ways of allocating payments.

Trained on 1,500 messages using the tuning phrasings. Word regularisation 0.03 and emergency threshold 0.12 were chosen by cross-validation holding out whole phrasings (false-alarm budget 15.0%).

## Validation phrasings (seen while the lexicon was written)

17 kinds of problem, 35 phrasings.

| Messages | Emergencies caught | False alarms | Urgency right | Trade right |
|---|---:|---:|---:|---:|
| Keyword rules | 9.7% | 13.9% | 47.9% | 69.3% |
| Learned model, words only | 67.4% | 26.0% | 49.8% | 57.6% |
| Triage (hazard screen + model) | 100.0% | 15.6% | 62.7% | 88.9% |

Simulated months: 2,324 requests, 262 emergencies.

| Policy | Emergencies attended within 4 h | Median | 90th percentile | Worst | False alarms a week | At night |
|---|---:|---:|---:|---:|---:|---:|
| Inbox order, no triage | 139 of 262 (53.1%) | 3.6 h | 32.9 h | 62.8 h | 0.0 | 0.0 |
| Keyword rules flag emergencies | 148 of 262 (56.5%) | 3.4 h | 32.2 h | 62.8 h | 12.8 | 2.0 |
| Triage flags emergencies | 262 of 262 (100.0%) | 2.2 h | 3.0 h | 3.2 h | 12.8 | 2.1 |

## Fresh phrasings (written after the freeze): the test

17 kinds of problem, 68 phrasings.

| Messages | Emergencies caught | False alarms | Urgency right | Trade right |
|---|---:|---:|---:|---:|
| Keyword rules | 14.8% | 8.6% | 61.0% | 67.3% |
| Learned model, words only | 84.4% | 30.5% | 64.8% | 52.7% |
| Triage (hazard screen + model) | 90.4% | 19.3% | 71.5% | 77.2% |

Simulated months: 3,235 requests, 311 emergencies.

| Policy | Emergencies attended within 4 h | Median | 90th percentile | Worst | False alarms a week | At night |
|---|---:|---:|---:|---:|---:|---:|
| Inbox order, no triage | 160 of 311 (51.4%) | 3.7 h | 28.5 h | 62.3 h | 0.0 | 0.0 |
| Keyword rules flag emergencies | 184 of 311 (59.2%) | 3.2 h | 25.1 h | 61.6 h | 8.3 | 1.3 |
| Triage flags emergencies | 301 of 311 (96.8%) | 2.2 h | 3.1 h | 23.1 h | 17.6 | 3.1 |

Emergencies triage missed (sample):

- Good morning, someone tried to force the lock and now it won't close upstairs.
- Good morning, the bathroom ceiling has come down in the kitchen since this morning.
- Hello, the plug socket in the bedroom went bang and is black in the bathroom. We have a baby at home. Cheers
- Hey, Please help ASAP! the plug socket in the bedroom went bang and is black upstairs since yesterday. Thank you!
- Hey, When you get a chance: the bedroom window frame fell out in the wind in the kitchen since yesterday. My mum is elderly and lives with us.
- Hey, the bedroom window frame fell out in the wind in the bathroom since last night. Thank you!
- Hi there, EMERGENCY: someone tried to force the lock and now it won't close in the kitchen. I work from home. Cheers
- Hi, No rush, but the bedroom window frame fell out in the wind in flat 4B. My mum is elderly and lives with us.

## Tuning (phrasing-held-out cross-validation)

| Word L2 | Threshold | Emergencies caught | Urgency right | Trade right |
|---:|---:|---:|---:|---:|
| 0.001 | 0.14 | 95.8% | 67.5% | 90.3% |
| 0.01 | 0.14 | 95.8% | 69.1% | 94.5% |
| 0.03 | 0.12 | 95.8% | 70.1% | 94.5% |
| 0.1 | 0.11 | 95.8% | 70.5% | 93.9% |
| 0.3 | 0.1 | 95.8% | 70.2% | 93.9% |

## Rent ledger: a year, 5 portfolios

| Allocation | Late fees | Fees total | Fees while all rent was paid | Paid all rent, shown owing rent |
|---|---:|---:|---:|---:|
| rent first | 1,639 | $81,950 | 0 | 0 of 904 |
| oldest first | 3,395 | $169,750 | 1,756 | 286 of 904 |

## Gate (regression limits)

PASSED
