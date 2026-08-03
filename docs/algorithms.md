# Algorithms

## Bridging factorisation

Implemented in `api/sabha/services/factorisation.py`.

Let `v(i, j)` be participant `i`'s vote on statement `j`, encoded as `+1`
for agree and `-1` for disagree. A pass, or a statement never shown to a
participant, is absent from the matrix, never a stored zero: zero is not
on the agree or disagree scale, and treating a missing vote as zero would
tell the model something no one said. The matrix is typically above 95
per cent missing, since nobody votes on everything.

Fit, over observed entries only:

```
v(i, j)  ~=  mu(j) + b(i) + < f(i), g(j) >
```

where `mu(j)` is the statement's bridging score, `b(i)` is participant
`i`'s general propensity to agree regardless of the statement, `f(i)` is
the participant's position in a low dimensional opinion space, and
`g(j)` is how strongly statement `j` loads on that space.

The bridging score is `mu(j)`. A statement that appeals only to one
faction is explained by the interaction term `< f(i), g(j) >`, which
absorbs the factional variance and leaves the intercept small. A
statement that most people accept regardless of where they sit has
nothing left for the interaction term to explain, so its intercept
stays high.

### Fitting

Fit by alternating least squares over observed entries only, no matrix
factorisation library. Each alternating step is a small, closed form
ridge regression:

- `mu(j)` is a ridge shrunk mean of the residual across everyone who
  voted on statement `j`: `sum(residual) / (n_j + lambda_mu)`.
- `b(i)` is the same shrinkage across every statement participant `i`
  voted on.
- `f(i)` solves `(Gᵀ G + lambda_f I) f = Gᵀ r` for the statements `i`
  voted on, where `G` stacks their `g(j)` rows and `r` is the residual
  after removing `mu` and `b`.
- `g(j)` is the symmetric update, solving against the `f(i)` rows of
  everyone who voted on `j`.

`lambda_mu` is deliberately the weakest of the four penalties. Shrinking
`mu(j)` less than `f`, `g`, and `b` biases the fit towards explaining
agreement as broad rather than factional, which is the conservative
direction: the model has to work harder to explain a statement's
popularity away as factional than to simply credit it to the intercept.

Fitting is deterministic given identical inputs and parameters. The only
randomness is the initial draw of `f` and `g`, seeded from
`FactorisationParams.seed`; every update after that is a fixed sequence
of closed form solves, so refitting the same snapshot reproduces
identical figures.

### Opinion clustering

Implemented in `api/sabha/services/clustering.py`.

Opinion clusters for display are obtained by running k-means, written by
hand with Lloyd's algorithm, on the fitted `f(i)` vectors, with `k`
chosen by silhouette score over a small range. Named factions are a
display convenience only: the bridging ranking above does not depend on
getting `k` right.

### Persisted snapshots

`api/sabha/services/model_run.py` fits a consultation's full observed
vote set and writes the result as a `model_run` row: every statement's
intercept, every participant's factor vector and bias, the fitted
loadings, and the cluster assignment. Rows are inserted fresh on every
refit, never updated, so a figure shown to the public against one run's
id can always be reproduced by refitting with that run's own parameters.

## Adaptive statement selection

## Coordination detection

## Escalation as optimal stopping
