# Statistical analysis

Run from the package root:

```sh
python3 -m pip install -r analysis/requirements.txt
python3 analysis/analyze.py
```

Each row in session-data.csv represents one participant's task session. private_rate and public_rate are pass rates between 0 and 1; weighted_total is the weighted NASA-TLX score. The condition values contextbranch and linear denote GitChat and Linear, respectively.

Correctness analysis uses within-participant differences in percentage points, adjusted for task and period, with HC3 standard errors and two-sided t inference. Workload analysis uses 100,000 paired bootstrap samples of participants. Results are written to results.json.
