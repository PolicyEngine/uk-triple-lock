"""Annual bootstrap VAR with a four-year statutory-gap bridge; no engine imports.

Calendar CPI and OBR-definition earnings use history_data's annual definitions.
The gap blocks jointly preserve four years of statutory-minus-calendar timing
errors, but are independent of calendar shocks. Only pre-origin years are used.
"""

import hashlib

import numpy as np

from .history_data import history
from .ts_methods import boot_var, shift
from . import ts_monthly

BLOCK_LENGTH = 4


def statutory_gaps(last_year):
    months, cpi, awe, _ = ts_monthly.levels((last_year, 12))
    years, calendar = history(first_year=2001, last_year=last_year)
    m = ts_monthly.annual_measures(months, cpi[None], awe[None], years)
    statutory = np.stack([m['statutory_cpi'][0], m['statutory_earnings'][0]], axis=1)
    return years, statutory - calendar


def paths(years, n, seed, end_obs=None, calendar_target=None):
    """Same annual-measure interface as ts_monthly.paths, with exact calendar means.

    At the current origin, calendar 2026 is unobserved but May–July AWE is
    observed and is pasted into that statutory cell. A year-end backtest has
    no partially observed future cells. Gap blocks are demeaned by position.
    """
    months, cpi, awe, _ = ts_monthly.levels(end_obs)
    last_year = months[-1][0] - (months[-1][1] < 12)
    _, data = history(first_year=1989, last_year=last_year)
    future = list(range(last_year + 1, max(years) + 1))
    cal, info = boot_var(data, len(future), n, seed)
    info['calendar_draw_sha256'] = hashlib.sha256(cal.tobytes()).hexdigest()
    if calendar_target is not None:
        unknown = set(calendar_target) - set(future)
        if unknown:
            raise ValueError(f'calendar targets must be future years: {sorted(unknown)}')
        cols = [future.index(y) for y in sorted(calendar_target)]
        cal[:, cols] = shift(cal[:, cols], np.array([calendar_target[y] for y in sorted(calendar_target)]))
    gy, g = statutory_gaps(last_year)
    starts = [j for j in range(len(gy) - BLOCK_LENGTH + 1)
              if gy[j + BLOCK_LENGTH - 1] == gy[j] + BLOCK_LENGTH - 1]
    if not starts:
        raise ValueError('no complete pre-origin statutory-gap blocks')
    blocks = np.array([g[j:j + BLOCK_LENGTH] for j in starts])
    blocks -= blocks.mean(axis=0, keepdims=True)
    pick = np.random.default_rng(seed + 7).integers(0, len(blocks), size=(n, (len(future) + 3) // 4))
    bridge = blocks[pick].reshape(n, -1, 2)[:, :len(future)]
    stat = cal + bridge
    # Copy statutory observations already published at a partially observed origin.
    idx = {m: i for i, m in enumerate(months)}
    for j, y in enumerate(future):
        if (y, 9) in idx:
            stat[:, j, 0] = cpi[idx[(y, 9)]] / cpi[idx[(y - 1, 9)]] - 1
        if (y, 7) in idx:
            stat[:, j, 1] = (np.mean([awe[idx[(y, m)]] for m in (5, 6, 7)]) /
                              np.mean([awe[idx[(y - 1, m)]] for m in (5, 6, 7)]) - 1)
    cols = [future.index(y) for y in years]
    info.update({'shocks': 'boot', 'gap_block_length': BLOCK_LENGTH,
                 'gap_block_starts': [gy[j] for j in starts], 'gap_blocks_demeaned': True,
                 'gap_block_sha256': hashlib.sha256(pick.tobytes()).hexdigest(),
                 'last_training_year': last_year, 'calendar_shifted': calendar_target is not None})
    return {'calendar_cpi': cal[:, cols, 0], 'calendar_earnings': cal[:, cols, 1],
            'statutory_cpi': stat[:, cols, 0], 'statutory_earnings': stat[:, cols, 1]}, info
