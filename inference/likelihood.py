"""Log likelihoods for the two reported three-coordinate frames."""

from math import erfc, expm1, fsum, inf, log, pi, sqrt


def residuals(observed, modeled):
    return tuple(q - mu for a, b in zip(observed, modeled, strict=True)
                 for q, mu in zip(a, b, strict=True))


def gaussian_log_likelihood(observed, modeled, sigma):
    delta = residuals(observed, modeled)
    return -0.5 * fsum((d / sigma) ** 2 for d in delta) - len(delta) * log(sigma * sqrt(2 * pi))


def correlated_gaussian_log_likelihood(observed, modeled, cholesky):
    """Use a lower Cholesky factor of the covariance in frame order."""
    delta = residuals(observed, modeled)
    whitened = []
    log_diagonal = []
    for i, (d, row) in enumerate(zip(delta, cholesky, strict=True)):
        diagonal = row[i]
        whitened.append((d - fsum(row[j] * w for j, w in enumerate(whitened))) / diagonal)
        log_diagonal.append(log(diagonal))
    return -0.5 * (fsum(w * w for w in whitened) + len(delta) * log(2 * pi)) - fsum(log_diagonal)


def log_survival(z):
    if z < 26:
        return log(0.5 * erfc(z / sqrt(2)))
    # Mills ratio expansion avoids underflow far in the Gaussian tail.
    inv_z2 = (1 / z) ** 2
    correction = 1 - inv_z2 * (1 - inv_z2 * (3 - inv_z2 * (15 - 105 * inv_z2)))
    return -0.5 * z * z - log(z) - 0.5 * log(2 * pi) + log(correction)


def rounded_log_likelihood(observed, modeled, width, sigma=0.0):
    """Independent rounded Gaussian observations, or rounding alone at sigma=0."""
    half = width / 2
    delta = residuals(observed, modeled)
    if sigma == 0:
        return 0.0 if all(-half < d <= half for d in delta) else -inf

    terms = []
    for d in delta:
        # Reflect to the positive tail when the interval midpoint is negative.
        center = abs(d)
        lower, upper = (center - half) / sigma, (center + half) / sigma
        log_lower = log_survival(lower)
        log_upper = log_survival(upper)
        difference = log_upper - log_lower
        if difference < 0:
            terms.append(log_lower + log(-expm1(difference)))
        else:
            # Endpoints coincide at floating-point precision for a narrow cell.
            terms.append(log(width) - log(sigma) - 0.5 * log(2 * pi)
                         - 0.5 * (center / sigma) ** 2)
    return fsum(terms)
