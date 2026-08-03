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

### Downweighting a coordinated block

`fit()` takes an optional per-participant weight, defaulting every
participant to 1.0. A weight below that, as `coordination.py` assigns to
a detected brigade, scales that participant's row only in the `mu(j)`
and `g(j)` updates, the two that aggregate across everyone who voted on
a statement:

```
mu(j) = sum(w_i * residual_i) / (sum(w_i) + lambda_mu)
```

and the symmetric weighted normal equations for `g(j)`. `b(i)` and
`f(i)` stay at full weight, fit only from that participant's own votes,
so a downweighted participant still gets an honest personal position;
only their pull on what a statement means to the room at large is
reduced. This is section 6.4 of the project description: degrade a
coordinated block's influence, do not erase it.

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

Implemented in `api/sabha/services/selection.py`.

A random statement order wastes votes: a participant on a slow
connection gives eight votes, not sixty, so each one has to earn its
place. This is treated as sequential experimental design in two phases.

**Locate.** A participant's opinion position `f(i)` is fit from the
statements they have voted on by the same ridge regression as the main
model. Under a Gaussian approximation, its posterior covariance is

```
Cov(f(i)) = (G_i^T G_i + lambda_f I)^-1
```

where `G_i` stacks the fitted `g(j)` of every statement `i` has voted
on. Its trace is the posterior width tracked here. With no votes yet,
`G_i` is empty and the width is `num_factors / lambda_f`, the widest it
gets. While the width sits above a threshold, the next statement served
is whichever eligible candidate has the largest loading norm `|g(j)|`,
since a statement that discriminates strongly along the opinion axes
moves the estimate the most per vote. This is a rule of thumb version
of the full D-optimal design the project description names: the exact
version would rank candidates by the Sherman-Morrison reduction in
`trace(Cov(f(i)))` from adding each one, which is more expensive to
evaluate per vote for the same qualitative choice.

**Refine.** Once the width falls under the threshold, the objective
switches to the statement's own posterior. Under the same ridge
interpretation, `mu(j)`'s posterior variance is `1 / (n_j + lambda_mu)`,
so the statement with the fewest votes so far is the most uncertain,
and a vote from an already well placed participant resolves it fastest.

Exposure is capped per statement so no statement accumulates votes
indefinitely, and a small fraction of slots, `reserve_fraction`, is
always chosen uniformly at random regardless of phase, so the policy
cannot become self-confirming by only ever asking about what it already
suspects.

## Coordination detection

Implemented in `api/sabha/services/coordination.py`.

An organised group voting in concert produces near identical rows in
the vote matrix. A participant similarity graph is built over pairs
that share at least `min_overlap` voted statements, weighted by the
cosine similarity of their votes restricted to that shared set.
`min_overlap` defaults to 15: below that, two genuinely independent
participants can agree by chance often enough to cross a high
similarity threshold on a small shared sample, which chains unrelated
people into one spurious component under single link clustering. At 15
shared votes that chance agreement falls away on the seed corpus, while
a real brigade's deliberately identical votes stay at a similarity of
1.0 regardless of sample size.

The graph is thresholded at `similarity_threshold` and split into
connected components with `scipy.sparse.csgraph.connected_components`,
which keeps this to the sparse module the stack already allows rather
than adding a general graph library for one function. A component is
flagged as coordinated only if it is both large enough
(`min_cluster_size`) and dense enough (`density_threshold` of the
`n choose 2` possible internal edges are present): a real brigade forms
a near clique, so both bars clear easily, while a genuine loose
community, correlated but not lockstep, rarely forms a clique at a
similarity threshold this high even when its members agree often.

A flagged participant's weight is set to `downweight_factor`, not to
zero, and passed to `factorisation.fit()`. Every flag carries a
`CoordinationEvidence` record: the member ids, the internal density, the
mean similarity, and the mean shared vote count, so the decision is
auditable rather than a bare number.

## Escalation as optimal stopping
