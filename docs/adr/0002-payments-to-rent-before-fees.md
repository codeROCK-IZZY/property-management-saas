# 2. Apply payments to rent before fees

## Context

Most tenants pay the rent amount and nothing else. When a payment arrives, the ledger has to decide which open
charges it pays. The simplest rule, and a common one, is strictly oldest first: an unpaid late fee from March is paid
before April's rent.

That rule has a known failure. One late month leaves a fee open. The next full rent payment pays the fee first, so
that month's rent is a little short. The shortfall is still open after the grace period, so a new fee is charged, and
so on every month: one late payment becomes a fee every month, although the tenant pays the full rent on time. Lenders
call this fee pyramiding, and in lending it is banned. For a tenant it can be worse: the ledger shows rent owed, and
in many places unpaid rent (not unpaid fees) is the ground for starting an eviction.

## Decision

- A payment goes to open **rent** first, oldest month first, then to open fees, oldest first. Anything left is
  credit and is used by the next charges as they are made.
- A late fee is charged **once per month**, only when that month's rent is still open after the grace period. It is
  a flat amount or a percentage of the rent, capped.
- Rent for a part month is prorated by the days let, out of the days in that month.
- Strictly oldest-first allocation is kept as an option, so the evaluation can compare the two on the same payments.

## Consequences

A simulated year of 1,000 tenants (5 portfolios; most pay on time, some late once, some often late, a few short; nobody
pays fees separately), with exactly the same payments run through both ledgers:

| Allocation | Late fees | Fees charged while all rent was paid | Paid all rent, shown owing rent |
|---|---:|---:|---:|
| Rent first (this ledger) | 1,639 | **0** | **0 of 904** |
| Strictly oldest first | 3,395 | 1,756 | 286 of 904 |

- Strictly oldest first more than doubled the fees, and more than half of them were charged to tenants who had paid
  every cent of rent charged so far. 286 tenants who paid all their rent would be shown owing rent.
- Fees left unpaid stay visible as fees, separate from rent. Collecting them is a decision for a person, not a side
  effect of how a payment was split.
- The evaluation gate fails if the rent-first ledger ever charges a fee while all rent is paid, or shows a fully paid
  tenant owing rent.
- Late fees are kept by the manager in this demo; they are not part of the owner's statement. Many agreements share
  them; that would be a setting.
