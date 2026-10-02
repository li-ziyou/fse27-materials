# Scoring

Requires Python 3.11 or later and pytest. Run from the package root:

```sh
python3 -m pip install pytest
python3 evaluation/score.py
```

The output, scores.csv, has one row per task session. Each task has nine public tests. The tree task has 20 private tests, and the matching task has 17. The snapshot index specifies form F1 or F2. Import failures count as non-passing outcomes. After a suite timeout, tests run individually; tests that still time out count as non-passing. Scoring runs in temporary directories.

The rerun reproduced all 72 private-test scores in the manuscript analysis data. For P008 in GitChat, the public-test rerun produced 4/9, whereas the existing analysis table reports 5/9. The original analysis input has not been changed. This difference does not affect the private-test effectiveness results.
