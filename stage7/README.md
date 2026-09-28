# Stage 7B production integration

Ivana's `LoadComponent`, `FlexibilityClass`, `FlexibilityConstraint`, and
A/B/C/D component classification are preserved in `contract/schema.py` and
`constraints/stage7_constraints.py`. Static point quantities in those rules
are display/mock representatives only.

Production consumers add `stage7/backend` to their import path and call:

```python
from hackowatt_stage7 import build_optimization_requirements

requirements = build_optimization_requirements()
```

The builder reads only the frozen Stage 3A/3B ledgers, Stage 3B hourly state,
and Stage 3B metadata. It does not import or call Ivana's mock generator.
`requirements.events` contains concrete EV, pool circulation, dishwasher,
washer, dryer, sauna, and pool-heating requirements. `requirements.hvac`
contains separate heating/cooling comfort bands and the unchanged recurrence
inputs plus hourly occupancy/AWAY targets.

`ProductionEventConstraint.availability_intervals` uses half-open operating
intervals or feasible-start support, identified by `availability_semantics`.
For EVs with no next departure recorded inside the frozen ledger, the home
availability interval has a nullable end and no invented deadline. Boundary
accounting remains explicit in `boundary_truncated`,
`delivered_in_window_kwh`, and `remaining_energy_kwh`.
