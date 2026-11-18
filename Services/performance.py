import numpy as np
import pandas as pd

TRADING_DAYS = 252
ANNUAL_RISK_FREE_RATE = 0.04
BENCHMARK_ANNUAL_RETURN = 0.08
DRIFT_SHRINKAGE = 0.5
MAX_ANNUAL_DRIFT = 0.20
MIN_ANNUAL_DRIFT = -0.20


def compute_returns(prices):
    return prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna()


def compute_portfolio_returns(returns, weights):
    return returns.mul(weights.reindex(returns.columns, fill_value=0)).sum(
        axis=1, min_count=len(returns.columns)
    )


def compute_ttwr(portfolio_returns):
    return (
        None
        if portfolio_returns is None or portfolio_returns.empty
        else (1 + portfolio_returns).prod() - 1
    )


def drawdowns(returns):
    wealth = (1 + returns).cumprod()
    return wealth / wealth.cummax().clip(lower=1) - 1


def drawdown_summary(returns):
    """Worst fall from a high, how far below its high it is now, and the
    longest stretch spent below a previous high (in calendar days)."""
    dd = drawdowns(returns.dropna())
    if dd.empty:
        return None
    worst_date = dd.idxmin()
    below = dd < -1e-9
    longest, longest_recovered, start = 0, True, None
    index = list(dd.index)
    for i, flag in enumerate(below):
        if flag and start is None:
            start = index[i - 1] if i else index[i]
        if not flag and start is not None:
            span = (index[i] - start).days if hasattr(index[i], "day") else i
            if span > longest:
                longest, longest_recovered = span, True
            start = None
    if start is not None:
        span = (index[-1] - start).days if hasattr(index[-1], "day") else len(index)
        if span >= longest:
            longest, longest_recovered = span, False
    return {
        "worst": float(dd.min()),
        "worst_date": worst_date,
        "current": float(dd.iloc[-1]),
        "longest_days": int(longest),
        "longest_recovered": longest_recovered,
    }


def compute_performance_metrics(
    portfolio_returns, benchmark_returns, risk_free=ANNUAL_RISK_FREE_RATE
):
    paired = (
        pd.concat(
            [portfolio_returns.rename("p"), benchmark_returns.rename("b")], axis=1, join="inner"
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .sort_index()
    )
    if len(paired) < 2:
        return dict.fromkeys(["sharpe", "sortino", "beta", "alpha", "max_drawdown"])
    daily_rf = np.expm1(np.log1p(risk_free) / TRADING_DAYS)
    excess = paired.p - daily_rf
    annual_excess = excess.mean() * TRADING_DAYS
    vol = paired.p.std() * np.sqrt(TRADING_DAYS)
    downside = np.sqrt(np.mean(np.minimum(excess, 0) ** 2)) * np.sqrt(TRADING_DAYS)
    variance = paired.b.var()
    beta = paired.p.cov(paired.b) / variance if variance > 1e-20 else None
    alpha = (
        (excess.mean() - beta * (paired.b - daily_rf).mean()) * TRADING_DAYS
        if beta is not None
        else None
    )
    return dict(
        sharpe=annual_excess / vol if vol > 0 else None,
        sortino=annual_excess / downside if downside > 0 else None,
        beta=beta,
        alpha=alpha,
        max_drawdown=drawdowns(paired.p).min(),
    )


def valid_covariance(returns):
    complete = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(complete) < 2 or complete.shape[1] == 0:
        raise ValueError("At least two common observations are required.")
    cov = complete.cov().to_numpy(float)
    eigenvalues, eigenvectors = np.linalg.eigh((cov + cov.T) / 2)
    if eigenvalues.min() < -1e-10:
        raise ValueError("Invalid covariance matrix.")
    return (eigenvectors * np.maximum(eigenvalues, 0)) @ eigenvectors.T


def risk_contributions(returns, weights):
    cov = valid_covariance(returns)
    w = weights.reindex(returns.columns).to_numpy(float)
    variance = float(w @ cov @ w)
    if variance <= 0:
        return pd.Series(0.0, index=returns.columns)
    return pd.Series(w * (cov @ w) / variance, index=returns.columns)


RISK_HEAVY = 1.10  # flag holdings with at least 10% more risk than money


def risk_vs_weight(returns, weights):
    """Per holding: capital weight, share of portfolio variance, their ratio and
    standalone annualized volatility, sorted with the most risk-heavy first.

    Risk contribution includes each holding's share of its covariance with the
    others; standalone volatility is the holding on its own.
    """
    contributions = risk_contributions(returns, weights)
    cov = valid_covariance(returns)
    w = weights.reindex(returns.columns).astype(float)
    table = pd.DataFrame(
        {
            "weight": w,
            "risk": contributions,
            "ratio": (contributions / w).where(w > 0),
            "volatility": pd.Series(np.sqrt(np.diag(cov) * TRADING_DAYS), index=returns.columns),
        }
    )
    return table.sort_values(["ratio", "risk"], ascending=False)


def risk_takeaway(table):
    """One plain sentence on where risk sits compared with money."""
    heavy = table[table["ratio"] >= RISK_HEAVY]
    if heavy.empty:
        return "No holding adds noticeably more risk than its share of your money."
    names = list(heavy.index)
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    verb = "is" if len(names) == 1 else "are"
    return (
        f"{listed} {verb} {heavy['weight'].sum():.0%} of your money but "
        f"{heavy['risk'].sum():.0%} of your risk."
    )


def portfolio_growth(log_returns, weights):
    return np.exp(log_returns) @ np.asarray(weights)


SHOCK_MODELS = ("normal", "student_t", "bootstrap")
STUDENT_T_DF = 4  # heavy tails, still finite variance
REGIME_DAYS = 21  # bootstrap block length (about a month), keeping real crash sequences


def simulate_paths(
    returns,
    weights,
    initial_value,
    years,
    simulations,
    seed=42,
    long_run=BENCHMARK_ANNUAL_RETURN,
    shrinkage=DRIFT_SHRINKAGE,
    cap=MAX_ANNUAL_DRIFT,
    shocks="normal",
):
    """Illustrative scenarios under stated assumptions, not a forecast.

    long_run: annual return each holding's expected return is pulled toward.
    shrinkage: weight on the holding's own history (0 = all long_run, 1 = all history).
    cap: expected annual returns are clipped to +/- cap.
    shocks: "normal" (independent Gaussian days);
        "student_t" (fat tails: each simulated year draws its own volatility
        level from a Student-t mixing distribution, so some scenario-years are
        calm and some are crisis-like; same average variance as "normal");
        "bootstrap" (month-long blocks of actual history, keeping real crash
        sequences, fat tails and crisis correlations, re-centred on the same
        expected returns).
    Fat-tailed single days alone would average out over a year, which is
    why both alternatives keep shocks clustered.
    """
    if not np.isfinite(initial_value) or initial_value <= 0:
        raise ValueError("Modeled starting value must be positive and finite.")
    years, simulations = int(years), int(simulations)
    if years not in (1, 3, 5) or simulations not in (500, 1000, 5000, 10000):
        raise ValueError("Unsupported simulation size.")
    long_run, shrinkage, cap = float(long_run), float(shrinkage), float(cap)
    if not -0.5 < long_run < 0.5:
        raise ValueError("Expected yearly return must be between -50% and 50%.")
    if not 0 <= shrinkage <= 1:
        raise ValueError("Trust in past performance must be between 0% and 100%.")
    if not 0 < cap <= 1:
        raise ValueError("Limit per stock must be above 0% and at most 100%.")
    if shocks not in SHOCK_MODELS:
        raise ValueError("Unknown shock model.")
    complete = returns.replace([np.inf, -np.inf], np.nan).dropna()
    covariance = valid_covariance(complete)
    # Shrink annual arithmetic expected returns, then convert to log drift.
    arithmetic = np.expm1(complete).mean() * TRADING_DAYS
    expected = (shrinkage * arithmetic + (1 - shrinkage) * long_run).clip(-cap, cap).to_numpy()
    mean = np.log1p(expected) / TRADING_DAYS - 0.5 * np.diag(covariance)
    w = weights.reindex(complete.columns).to_numpy(float)
    if not np.isfinite(w).all() or (w < 0).any() or not np.isclose(w.sum(), 1):
        raise ValueError("Simulation weights must be nonnegative and total 100%.")
    steps = years * TRADING_DAYS
    values = np.empty((steps + 1, simulations))
    values[0] = initial_value
    rng = np.random.default_rng(seed)
    centred = (complete - complete.mean()).to_numpy()
    for start in range(0, simulations, 250):
        stop = min(start + 250, simulations)
        size = (steps, stop - start)
        blocks = -(-steps // REGIME_DAYS)
        if shocks == "bootstrap":
            block = min(REGIME_DAYS, len(centred))
            starts = rng.integers(0, len(centred) - block + 1, size=(blocks, size[1]))
            index = (starts[:, None, :] + np.arange(block)[None, :, None]).reshape(-1, size[1])
            samples = centred[index[:steps]] + mean
        elif shocks == "student_t":
            # Gaussian shocks divided by sqrt(chi2/df), drawn once per simulated year and
            # shared by every holding: a multivariate t with the same covariance on average.
            scale = covariance * (STUDENT_T_DF - 2) / STUDENT_T_DF
            normal = rng.multivariate_normal(
                np.zeros(len(mean)), scale, size=size, check_valid="raise"
            )
            years_drawn = -(-steps // TRADING_DAYS)
            regime = np.sqrt(
                rng.chisquare(STUDENT_T_DF, size=(years_drawn, size[1])) / STUDENT_T_DF
            )
            mix = np.repeat(regime, TRADING_DAYS, axis=0)[:steps, :, None]
            samples = mean + normal / mix
        else:
            samples = rng.multivariate_normal(mean, covariance, size=size, check_valid="raise")
        growth = portfolio_growth(samples, w)
        values[1:, start:stop] = initial_value * np.cumprod(growth, axis=0)
    return np.arange(steps + 1) / TRADING_DAYS, values
