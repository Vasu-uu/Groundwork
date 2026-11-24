# Groundwork eval results

Provider `demo`, model `hand-labelled-replay`, run 2026-11-24 10:32 UTC.

| Sample set | Interviews | Verified quotes | Verdict agreement | Stance agreement | Pain-quote recall | Calls (failed) | Tokens | Time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| freelance-invoicing | 6 | 33/33 (100%) | 4/4 (100%) | 100% | 14/14 (100%) | 13 (0) | 11881 | 0s |
| physio-no-shows | 5 | 26/26 (100%) | 4/4 (100%) | 100% | 11/11 (100%) | 11 (0) | 9047 | 0s |
| restaurant-waste | 3 | 17/17 (100%) | 2/3 (67%) | 100% | 8/8 (100%) | 7 (0) | 5163 | 0s |

**Overall:** verified quotes 76/76 (100%), verdict agreement 10/11.

## freelance-invoicing

| Hypothesis | Label | AI suggestion | Stances matching |
| --- | --- | --- | --- |
| H1 | VALIDATED | VALIDATED | 6/6 |
| H2 | MIXED | MIXED | 6/6 |
| H3 | INVALIDATED | INVALIDATED | 6/6 |
| H4 | UNTESTED | UNTESTED | 6/6 |

## physio-no-shows

| Hypothesis | Label | AI suggestion | Stances matching |
| --- | --- | --- | --- |
| H1 | VALIDATED | VALIDATED | 5/5 |
| H2 | MIXED | MIXED | 5/5 |
| H3 | INVALIDATED | INVALIDATED | 5/5 |
| H4 | UNTESTED | UNTESTED | 5/5 |

## restaurant-waste

| Hypothesis | Label | AI suggestion | Stances matching |
| --- | --- | --- | --- |
| H1 | MIXED | MIXED | 3/3 |
| H2 | INVALIDATED | INVALIDATED | 3/3 |
| H3 | VALIDATED | MIXED ✗ | 3/3 |
