# Demo tasks

Use this list after `python -m app.seed` (or `--reset`). Employee credentials are printed by the seed command in the terminal, not in this file.

Amounts are shown as currency (`$1,234.56`). IDs keep leading zeros.

## Main investigation

1. Sign in, open **Member** in the blue bar, and search for member ID `001234`.
2. Open **Elena Vargas**. Confirm checking `CK-1001` and loan `LN-1001`.
3. Open `LN-1001`. The balance is labeled **Outstanding balance** and is **$3,532.08**.
4. Apply filters, then open a transaction and add an investigation note (enter → review → confirm). The success page shows a persisted note ID.
5. Refresh or retry confirm: a second note row must not appear for the same submission.

## Similar names

| Search | Expected |
| --- | --- |
| `Elena` | `001234` Elena Vargas and `001235` Elena Varga |
| `James` | `003100` James Okonkwo and `003101` James Okoye |

## Members and accounts

| ID | What to notice |
| --- | --- |
| `001234` | Replay target: checking `CK-1001`, loan `LN-1001` |
| `002001` | Marcus Chen, second-member loan `LN-2001` |
| `002010` | Priya Nair has checking `CK-2010` and savings `SV-2010`, and **no loan** |
| `SV-5500` | David Kim (`005500`) savings account with **no transactions** |
| `CK-4200` | Sofia Alvarez (`004200`) **inactive** checking account with historical transactions |

From a member profile, **Open account** creates checking or savings at `$0.00`. From Home, **Open loan** searches for a member and records an outstanding balance. From a member profile, **Order cheque book** (active members with an active checking account) debits a fee from a chosen checking/savings account and posts a `Cheque issue` transaction; success returns to the member profile with a debit acknowledgement. Types: Standard (25 pages, $15), Business (50 pages, $25), Premium (100 pages, $40).

## Amount filter (`LN-1001`)

Use **Amount strictly greater than** `500` (or `500.00`).

| Transaction | Amount | Included when threshold is $500? |
| --- | --- | --- |
| `TX-LN-1001-F01` | $250.00 debit | No |
| `TX-LN-1001-F04` | $499.99 debit | No |
| `TX-LN-1001-F02` | **exactly** $500.00 debit | **No** (strictly greater than) |
| `TX-LN-1001-F05` | $500.01 credit | Yes |
| `TX-LN-1001-F03` | $750.00 credit | Yes |
| `TX-LN-1001-F07` | $1,200.00 debit | Yes |

Fixture rows use descriptions that start with `FIXTURE`.

## January 2026 dates

Inclusive start/end dates on `LN-1001`:

| Transaction | Posted | Inside 2026-01-01 … 2026-01-31? |
| --- | --- | --- |
| `TX-LN-1001-F04` | 2026-01-05 | Yes |
| `TX-LN-1001-F07` | 2026-01-10 | Yes |
| `TX-LN-1001-F01` | 2026-01-15 | Yes |
| `TX-LN-1001-F02` | 2026-01-20 | Yes |
| `TX-LN-1001-F03` | 2026-01-25 | Yes |
| `TX-LN-1001-F05` | 2025-12-15 | No |
| `TX-LN-1001-F06` | 2026-02-01 | No |

Reversed ranges (start after end) show a validation error and do not list transactions.

## Pagination volume

Active accounts carry **thousands** of posted transactions overall (5,102 in the seed). Busy accounts have hundreds of rows (for example `CK-1001` has 620). The account register shows 10 rows per page and a result count such as `Showing 1–10 of 620 transactions.` Filters remain in the query string so Back from a transaction preserves them.

Seeded notes already exist on `TX-LN-1001-F02`, `TX-LN-1001-F03`, and `TX-LN-1001-F07`.

## Development scenarios

With `DEV_SCENARIOS_ENABLED=true`, open `/dev/scenarios` (not linked in the header):

- Session expiry → next member-services page requires sign-in; the original POST is not processed
- Slow results → next transaction search delays; the UI shows loading and disables resubmit
- Temporary error → next search fails once with **Retry**
- UI variation → **Apply Filters** is labeled **Search Transactions**
- Uncertain note → confirm saves the note, then shows an interrupted page; retry keeps a single note
- Reset → deletes local demo data, restores the seed, clears flags
