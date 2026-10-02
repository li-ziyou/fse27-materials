from pathlib import Path
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parent
data = pd.read_csv(ROOT / 'session-data.csv')
results = {}
for metric in ['private_rate', 'public_rate', 'weighted_total']:
    pair = data.pivot(index='participant', columns='condition', values=metric)
    scale = 100 if metric.endswith('_rate') else 1
    g = pair.contextbranch * scale
    l = pair.linear * scale
    delta = g - l
    conditions = data[data.condition == 'contextbranch'].set_index('participant').loc[pair.index]
    design = pd.DataFrame({'const': 1., 'task': np.where(conditions.task == 'tree-node-navigation', 1., -1.), 'period': np.where(conditions.period == 2, 1., -1.)}, index=pair.index)
    fit = sm.OLS(delta, design).fit(cov_type='HC3', use_t=True)
    item = {'n': len(pair), 'GitChat_mean': g.mean(), 'GitChat_sd': g.std(), 'Linear_mean': l.mean(), 'Linear_sd': l.std(), 'paired_difference': delta.mean()}
    if metric.endswith('_rate'):
        item.update(adjusted_difference=fit.params['const'], adjusted_CI95=fit.conf_int().loc['const'].tolist(), HC3_p=fit.pvalues['const'])
    else:
        rng = np.random.default_rng(20260918)
        values = delta.to_numpy()
        means = values[rng.integers(0, len(values), (100000, len(values)))].mean(axis=1)
        item['paired_bootstrap_CI95'] = np.quantile(means, [.025, .975]).tolist()
    results[metric] = item
(ROOT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
