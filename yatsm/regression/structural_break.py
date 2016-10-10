# -*- coding: utf-8 -*-
""" Methods for estimating structural breaks in time series regressions

TODO: extract and move Chow test from "commission test" over to here
"""
from __future__ import division

from collections import namedtuple
import logging

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy import stats
from scipy.stats import norm
import xarray as xr

from _recresid import _recresid
from ..accel import try_jit

logger = logging.getLogger(__name__)

pnorm = norm.cdf

pandas_like = (pd.DataFrame, pd.Series, xr.DataArray)

# tuple: CUSUM-OLS results
CUSUMOLSResult = namedtuple('CUSUMOLSResult', ['index', 'score', 'cusum',
                                               'pvalue', 'signif'])

# dict: CUSUM OLS critical values
CUSUM_OLS_CRIT = {
    0.01: 1.63,
    0.05: 1.36,
    0.10: 1.22
}


@try_jit(nopython=True, nogil=True)
def _cusum(resid, ddof):
    n = resid.size
    df = n - ddof

    sigma = ((resid ** 2).sum() / df * n) ** 0.5
    process = resid.cumsum() / sigma
    return process


@try_jit(nopython=True, nogil=True)
def _cusum_OLS(X, y):
    n, p = X.shape
    beta = np.linalg.lstsq(X, y)[0]
    resid = np.dot(X, beta) - y

    process = _cusum(resid, p)
    _process = np.abs(process)
    score = _process.max()
    idx = _process.argmax()

    return process, score, idx


def _brownian_motion_pvalue(x, k):
    """ Return pvalue for some given test statistic """
    # TODO: Make generic, add "type='Brownian Motion'"?
    if x < 0.3:
        p = 1 - 0.1464 * x
    else:
        p = 2 * (1 -
                 pnorm(3 * x) +
                 np.exp(-4 * x ** 2) * (pnorm(x) + pnorm(5 * x) - 1) -
                 np.exp(-16 * x ** 2) * (1 - pnorm(x)))
    return 1 - (1 - p) ** k


def _cusum_rec_test_crit(alpha):
    """ Return critical test statistic value for some alpha """
    return brentq(lambda _x: _brownian_motion_pvalue(_x, 1) -  alpha, 0, 20)


@try_jit()
def _cusum_rec_efp(X, y):
    """ Equivalent to ``strucchange::efp`` for Rec-CUSUM """
    # Run "efp"
    n, k = X.shape
    w = _recresid(X, y, k)[k:]
    sigma = w.var(ddof=1) ** 0.5
    w = np.concatenate((np.array([0]), w))
    return np.cumsum(w) / (sigma * (n - k) ** 0.5)


@try_jit(nopython=True, nogil=True)
def _cusum_rec_sctest(x):
    """ Equivalent to ``strucchange::sctest`` for Rec-CUSUM """
    x = x[1:]
    j = np.linspace(0, 1, x.size + 1)[1:]
    x = x * 1 / (1 + 2 * j)
    stat = np.abs(x).max()

    return stat


def cusum_OLS(X, y, alpha=0.05):
    u""" OLS-CUSUM test for structural breaks

    Tested against R's ``strucchange`` package and is faster than
    the equivalent function in the ``statsmodels`` Python package when
    Numba is installed.

    # TODO: same function for cusum_REC?

    Args:
        X (array like): 2D (n_obs x n_features) design matrix
        y (array like): 1D (n_obs) indepdent variable
        alpha (float): Test threshold (either 0.01, 0.05, or 0.10) from
            Ploberger and Krämer (1992)

    Returns:
        CUSUMOLSResult: A named tuple include the the change point (index of
            ``y``), the test ``score`` and ``pvalue``, and a boolean testing
            if the CUSUM score is significant at the given ``alpha``
    """
    _X = X.values if isinstance(X, pandas_like) else X
    _y = y.values.ravel() if isinstance(y, pandas_like) else y.ravel()

    cusum, score, idx = _cusum_OLS(_X, _y)
    if isinstance(y, pandas_like):
        if isinstance(y, (pd.Series, pd.DataFrame)):
            index = y.index
            idx = index[idx]
        elif isinstance(y, xr.DataArray):
            index = y.to_series().index
            idx = index[idx]
        cusum = pd.Series(data=cusum, index=index, name='CUSUM')

    # crit = stats.kstwobign.isf(alpha)  ~70usec
    crit = CUSUM_OLS_CRIT[alpha]
    pval = stats.kstwobign.sf(score)

    return CUSUMOLSResult(index=idx, score=score, cusum=cusum,
                          pvalue=pval, signif=score > crit)


def cusum_recursive(X, y, alpha=0.05):
    u""" Rec-CUSUM test for structural breaks

    Tested against R's ``strucchange`` package.

    Critical values for this test statistic are taken from:

        A. Zeileis. p values and alternative boundaries for CUSUM tests.
            Working Paper 78, SFB "Adaptive Information Systems and Modelling
            in Economics and Management Science", December 2000b.
    """
    process = _cusum_rec_efp(X, y)
    stat = _cusum_rec_sctest(process)
    n, k = process.shape[0], 1
    stat_pvalue = _brownian_motion_pvalue(stat, k)

    pvalue_crit = _cusum_rec_test_crit(alpha)
    if stat_pvalue < alpha:
        boundary = (pvalue_crit +
                    (2 * pvalue_crit * np.arange(0, n) / (n - 1)))
        idx = np.where(np.abs(process) > boundary)[0]

    # TODO: pandas this up
    # TODO: cusum boundary function
    # TODO: design and return a namedtuple
    # TODO: think about making some functions public