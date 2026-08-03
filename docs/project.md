# Sabha

A consensus engine for public consultation that finds the positions people agree on across factional lines, evolves better framings for the positions they do not, and files the result with the department that has legal jurisdiction.

Theme: Social Innovation and Inclusive Development.

---

## 1. The problem

India runs public consultation at genuine scale. Pre-legislative consultation policy requires draft rules to be published for comment. MyGov, ministry portals, and departmental notices collect tens of thousands of citizen submissions on individual drafts. The Digital Personal Data Protection rules, the labour codes, and the e-commerce rules each drew comment volumes in the thousands.

Almost none of it is read.

The reason is not indifference. It is that there is no method. A ministry official handed 40,000 free text comments in nine languages has two options: sample a handful, or count keywords. Neither tells them anything useful. So consultation becomes a formality, the loudest organised lobby gets quoted in the press as though it were public opinion, and citizens learn that submitting a comment is a waste of an afternoon.

There is a second, deeper failure. Even when opinion is measured properly, it is measured as a majority. Majority counting on a polarised question returns the position of the largest bloc, which is precisely the position the other blocs will fight. It systematically discards the far more useful answer: what does almost everybody accept, including people who disagree about everything else.

## 2. What the system does

Sabha has four parts.

**It measures agreement in a way that survives polarisation.** Participants vote agree, disagree, or pass on short statements. From the resulting sparse vote matrix, the system fits a model that separates a statement's broad appeal from its factional appeal, and ranks by the former. A statement adored by one cluster and hated by another scores low. A statement that a majority of every cluster accepts scores high, even if no cluster is wild about it.

**It searches for better framings.** Where the model finds a fault line, meaning a statement that matters but divides, a generation loop proposes reformulations aimed at that specific divide, puts them in front of real participants, and keeps the ones that measurably bridge better than their parents. Fitness is observed human agreement, not a model's opinion about what should be agreeable.

**It defends itself.** Organised brigading is the normal condition of any open consultation, not an edge case. Coordinated accounts leave a detectable signature in the correlation structure of the vote matrix, and the system downweights them without requiring anyone to prove their identity.

**It files.** The output is not a report that nobody reads. It is a drafted clause set, each clause carrying the support figures that back it, routed to the ministry with statutory jurisdiction, submitted in that channel's required format, and tracked against the statutory reply clock with an escalation policy behind it.

## 3. Why the third and fourth parts matter

A tool that only surfaces consensus produces a beautiful dashboard and changes nothing. The interesting claim Sabha makes is that the last mile, actually reaching a department and holding it to a deadline, is a tractable software problem that nobody has built.

It also produces something valuable as a byproduct. A platform that files at volume, tracks replies, and scores whether those replies engaged with the substance accumulates a dataset that does not currently exist: per department response rate, median latency, template reply rate, and whether positions with demonstrated cross-factional support ever appeared in the final notified rules. That is a public responsiveness record for the Indian state, generated as exhaust from doing the primary job.

## 4. Prior art, and what is new

Naming prior art up front is not a weakness. It is the difference between a project that read the literature and a project that reinvented something worse.

**Polis** (Computational Democracy Project) is the origin of statement voting plus opinion clustering plus consensus surfacing. It powered vTaiwan and Taiwan's Join platform, and remains the reference implementation of the idea.

**Community Notes** on X ranks notes using a matrix factorisation where a note's intercept term captures the helpfulness that survives after viewpoint is factored out. This is a bridging metric operating at a scale of hundreds of millions of ratings, which is the strongest available evidence that the approach is not merely academic.

**The Habermas Machine** (Tessler et al., Science, October 2024) showed that language models can mediate group deliberation by generating group statements that increase agreement among participants who initially disagreed.

What Sabha adds, and what it should be judged on:

1. A closed generation loop where proposed framings are empirically selected on measured cross-factional agreement, rather than generated once and presented.
2. Adaptive statement selection, so a participant's position is located in eight to ten votes rather than sixty, which is what makes participation on a low end phone realistic.
3. Manipulation resistant aggregation designed in from the start rather than added after the first brigading incident.
4. An autonomous filing and escalation layer with legal jurisdiction routing, which no consultation tool has.

## 5. Architecture

```
Participants
   |
   v
Vote API  ->  Vote store (sparse)
                   |
                   v
        Bridging factorisation model
        (statement intercept, participant
         and statement factor loadings)
                   |
   +---------------+---------------+
   |               |               |
   v               v               v
Adaptive     Coordination     Bridging
selection    detection        ranking
(what to     (downweight      (what is
 show next)   brigades)        agreed)
                                   |
                                   v
                          Generation loop
                          (propose framings,
                           measure, select)
                                   |
                                   v
                          Clause drafting
                          + consensus certificate
                                   |
                                   v
                          Jurisdiction routing
                          (Allocation of Business Rules)
                                   |
                                   v
                          Filing agent (per channel)
                                   |
                                   v
                          Escalation scheduler
                          + reply evaluation
                                   |
                                   v
                          Accountability ledger
```

The division of labour is deliberate and should be stated whenever the project is presented. The language model does perception and language: reading messy multilingual submissions into structured statements, proposing reformulations, drafting clause text, and judging whether a reply engaged with the substance. Every decision that has to be defended, meaning what counts as consensus, who gets downweighted, when to escalate, and which department has jurisdiction, is made by deterministic code that a human can audit line by line.

## 6. Algorithms

### 6.1 Bridging factorisation

Let `v(i, j)` be participant `i`'s vote on statement `j`, encoded as `+1` for agree and `-1` for disagree. Passes and unseen statements are simply absent. The matrix is extremely sparse, typically above 95 per cent missing, because nobody votes on everything.

Fit, over observed entries only:

```
v(i, j)  ~=  mu(j) + b(i) + < f(i), g(j) >
```

where `mu(j)` is the statement intercept, `b(i)` is a participant's general propensity to agree, `f(i)` is participant `i`'s position in a low dimensional opinion space, and `g(j)` is how strongly statement `j` loads on that space.

The bridging score is `mu(j)`. This is the elegant part. A statement that appeals only to one faction is explained by the interaction term `< f(i), g(j) >`, which absorbs the factional variance and leaves the intercept small. A statement that most people accept regardless of where they sit has nothing for the interaction term to explain, so its intercept stays high.

Three properties matter:

- Missing votes need no imputation. Loss is computed on observed entries, which is the correct treatment of "did not see" and avoids the standard mistake of imputing zeros and then wondering why the clusters look wrong.
- Clustering becomes optional. Named factions are useful for the interface, but the ranking does not depend on getting `k` right.
- Regularisation carries a prior. L2 on `f` and `g` with a weaker penalty on `mu` biases the fit towards explaining agreement as broad rather than factional, which is the conservative direction. Say this when asked why the scores can be trusted.

Fit with alternating least squares or plain SGD over observed entries. Both are short enough to write by hand, and writing it by hand rather than importing it is the difference between being able to defend the model and not.

Opinion clusters for display are obtained by running k-means on the fitted `f(i)` vectors, with `k` chosen by silhouette score over a small range.

### 6.2 Adaptive statement selection

Random statement order wastes votes. A participant on a slow connection will give you eight votes, not sixty, so each one has to earn its place.

Treat it as experimental design in two phases.

**Locate.** While the posterior on `f(i)` is wide, serve statements with large `|g(j)|`. These are the discriminating ones, the statements whose answer tells you most about where somebody sits. Choose the statement maximising expected reduction in posterior variance of `f(i)`, which under a Gaussian approximation reduces to a closed form and is cheap to evaluate over a candidate pool.

**Refine.** Once `f(i)` is pinned down, switch objective. Serve statements whose `mu(j)` has the widest posterior, because a vote from a participant whose position is known is maximally informative about a statement whose score is uncertain.

Cap exposure per statement so that no statement accumulates votes indefinitely, and reserve a small random fraction of slots to avoid the selection policy becoming self-confirming.

### 6.3 Generation loop

Identify targets: statements with low `mu(j)` and high `|g(j)|`. These are the real fault lines, meaning positions that matter and divide, as opposed to positions nobody cares about.

For each target, construct a prompt containing the target statement, the cluster level agreement pattern, and a sample of statements each cluster already accepts. Ask for variants along specific axes: narrow the scope, concede one cluster's premise while preserving the other's substance, replace a contested value claim with a procedural one, separate a conjunction into its parts.

Inject variants into the live pool. Accumulate votes through the selection policy. After a minimum vote threshold, compare each variant's `mu` against its parent with a significance test, since comparing point estimates on small samples will manufacture progress that is not there. Retain winners, retire losers, and record the lineage so the provenance of every surviving statement is inspectable.

This is a genetic algorithm. Mutation is reformulation. Crossover is merging the substance of two statements. Fitness is measured human agreement. The population is the statement pool.

Two guardrails. Every generated statement is labelled as generated in the interface, always, with no exception, because a citizen has a right to know whether they are voting on a neighbour's words or a model's. And generation is capped as a fraction of the pool, so the deliberation cannot be flooded by machine output.

### 6.4 Coordination detection

An organised group voting in concert produces near identical rows in the vote matrix. Build a similarity graph over participants using cosine similarity of the observed vote overlap, restricted to pairs with sufficient overlap to make the comparison meaningful. Run community detection. Tight, unusually dense communities with near perfect internal agreement and short inter arrival times are the signature of coordination rather than of genuine shared opinion, which is looser and slower.

Downweight detected clusters in the factorisation rather than removing them, because being wrong about a real community should degrade their influence, not erase them. Surface every downweighting decision in the audit log with the evidence attached.

No identity verification is needed. The signal is in the structure of the behaviour.

### 6.5 Jurisdiction routing

The Allocation of Business Rules is a published legal instrument specifying which ministry is responsible for which subject. It is the authoritative ground truth, which means routing is a retrieval problem with a checkable answer rather than a guess.

Index the Rules and departmental mandates. For a drafted clause, retrieve candidate departments and have the model produce a routing decision with the specific rule entry cited. Treat it as multi label, because a clause about platform work genuinely belongs to Labour and to Electronics and Information Technology at once, and routing to one of them is how a submission dies quietly.

Any routing decision with low retrieval confidence goes to a human queue rather than being filed on a guess.

### 6.6 Escalation as optimal stopping

Filing immediately is wrong, and filing on the closing day is worse, because closing day submissions are processed in bulk. After filing, the question repeats: keep waiting, or escalate.

Model each department as a response time distribution estimated from observed history. The decision problem is then a Markov decision process over states of elapsed time and channel stage, with actions to wait or escalate, and a cost combining delay and the finite number of escalation steps available. Statutory structure makes it concrete: the Right to Information Act sets thirty days for a reply, then a First Appellate Authority, then the Information Commission. Solve by backward induction over a discretised time horizon, which is small enough to be exact.

### 6.7 Reply evaluation

For each reply, score whether it engaged with the clauses submitted or returned boilerplate. Substantive engagement is a model judgement over the reply against the original clauses, which is a reasonable use of a model since the stakes of a wrong call are low and the output is advisory.

Template detection is the more interesting half, and it works only at platform scale. Cluster replies received across many filings from the same department by near duplicate detection. A template reveals itself as a tight cluster of near identical text sent to unrelated submissions. An individual citizen cannot see this. A platform can see nothing else.

## 7. Data model

Core entities:

- **consultation**: the draft rule or question under discussion, with an open and close date and the responsible department once routed.
- **statement**: short text, author type of participant or generated, parent statement if it came from the generation loop, moderation state, language.
- **participant**: an anonymous session identity, a fitted factor vector, a weight after coordination adjustment.
- **vote**: participant, statement, value, timestamp. The only high volume table.
- **model_run**: a fitted snapshot with the intercepts, loadings, cluster assignments, and the parameters used, so any published figure can be reproduced exactly.
- **clause**: drafted text, the statements supporting it, its consensus certificate figures.
- **filing**: clause set, department, channel, artefact, submission timestamp, statutory deadline, current stage.
- **reply**: filing, received text, engagement score, template cluster if any.
- **ledger_entry**: an append-only record of every autonomous action, including what was filed, when, why, and by which policy decision.

Votes are immutable. Model runs are snapshots rather than in place updates. Both properties exist so that a figure shown to the public on a Tuesday can still be reproduced on a Friday, which is the minimum credibility requirement for anything that claims to represent public opinion.

## 8. Interface direction

The product is a public instrument for measuring agreement, and it should look like one. Not a startup dashboard, not a friendly civic app, and not a broadsheet pastiche.

The reference is the Indian government register: ruled ledger paper, numbered entries, mono figures in right aligned columns, rubber stamped endorsements. Rendered with precision rather than nostalgia, so it reads as a measuring instrument rather than a costume.

**Type.** Zilla Slab for display, used sparingly and only for page titles and the consensus certificate. IBM Plex Sans for body, with IBM Plex Sans Devanagari for Indic text, chosen because multilingual coverage is a functional requirement here and not a nice to have. IBM Plex Mono for every figure, statement code, and timestamp.

**Colour.** A pale ledger paper ground, cool near black ink, and a hairline rule colour. Faction colours are drawn from an explicitly arbitrary categorical palette and assigned by cluster index, so no reader can map a colour to a political party. A single reserved deep green appears in exactly one place in the entire application, which is the consensus certificate. A single reserved red appears only for escalation and coordination flags.

**Layout.** A visible baseline grid. Faint horizontal rules run through the interface, so it reads as a ledger. No shadows anywhere. No cards. Hairline borders. Radius capped at two pixels.

**Signature element.** The consensus certificate: a stamped endorsement block carrying the clause, the support figure inside every detected faction set in mono, the participant count, and the model run identifier. It is the only element allowed the reserved green and the only element with a heavy border. Everything else in the application stays quiet so that this one thing carries the weight.

**Second signature.** The opinion map draws each participant as a short tally stroke, angled by their factor loading, rather than as a dot. Tally marks are the vernacular of hand counting, the map reads as a field of strokes, and it does not look like every other scatter plot.

**Motion.** One orchestrated moment. Casting a vote settles the participant's own stroke into position on the map while the affected statement's bridging figure re-tallies with a short numeric roll. Nothing else animates. Reduced motion preference is respected and removes both.

## 9. Autonomous filing and safeguards

The filing layer acts on public institutions without a human in the loop for each action, so its constraints are part of the design rather than an afterthought.

- **One consolidated submission per consultation.** Not thousands of individual ones. A flood is a denial of service against a public system, it is indefensible, and it is self-defeating, because a single document backed by twelve thousand verified participants carries weight precisely by being one document.
- **No filing in an individual's name** without explicit per submission consent from that individual.
- **A human gate before the first filing** to any department the system has not filed to before.
- **Rate limits per department**, enforced in the scheduler and not merely recommended.
- **An append-only audit log** of every autonomous action, including the policy state that produced it, publicly readable.
- **Sandboxed by default.** The filing adapter ships pointed at a mock endpoint. Pointing it at a live government channel is a deliberate configuration change with a human confirmation, and during any demo it stays sandboxed.

## 10. Demonstration

Five minutes, in this order.

1. A question with real disagreement goes on screen with a QR code. The audience votes for three minutes on their own phones.
2. The opinion map builds live as strokes accumulate. Factions separate. Point out that most people were placed after roughly eight votes, and that this is the adaptive selection policy working rather than a coincidence.
3. Show the majority ranking next to the bridging ranking. They disagree. The statement the room actually agreed on is not the statement that won the most votes. This is the moment the idea lands, and it lands harder because the room is the dataset.
4. Run one generation. A model proposed reformulation of the most divisive statement enters the pool, collects votes from the room, and scores above its parent. A machine just wrote something the room agreed on more than anything a human in the room wrote.
5. Draft the clause, route it to a department with the rule entry cited, generate the filing artefact, dispatch it to the sandboxed endpoint, then compress the thirty day clock so the escalation fires on screen. Close on the ledger.

State from the stage that the filing endpoint is sandboxed. Volunteering that is the detail that makes an audience trust the rest.

## 11. Evaluation

Claims worth measuring, because a project that measures itself is more convincing than one that asserts:

- **Bridging quality**: minimum across cluster agreement of the top ranked statements, compared against a majority baseline on the same votes.
- **Selection efficiency**: votes needed to reach a fixed posterior width on `f(i)`, adaptive against random ordering.
- **Generation lift**: proportion of generated variants that significantly beat their parent's intercept, and the size of the gain.
- **Coordination recall**: on synthetic injected brigades of known size, the fraction detected and the false positive rate on genuine communities.
- **Routing accuracy**: against a hand labelled set of clauses with known correct ministries.

Report the failures alongside the successes. A project that says its coordination detector misses small brigades below a certain size is more credible than one that claims it catches everything.

## 12. Limitations

Stated plainly, because every one of these will be raised and pre-empting them is cheaper than defending them.

- Bridging optimises for what is broadly acceptable, which is not the same as what is correct. A well framed consensus can still be wrong, and a minority position can be right. The system is a measuring instrument for agreement, not an oracle for policy.
- Participation is self selected. Whoever is not online is not represented, and in India that skew is large and predictable. Report it rather than hiding it.
- The generation loop can find framings that are agreeable because they are vague. Penalise this explicitly with a specificity check, and accept that the tension does not fully resolve.
- Coordination detection cannot distinguish a genuine tightly aligned community from an organised campaign with certainty. It reduces influence, and it will sometimes be wrong.
- Language model routing and drafting will make errors. Everything they produce is checkable and cited for that reason.
- The real obstacle to consultation working in India is institutional will, not tooling. Software makes the failure visible and harder to sustain. It does not by itself fix it.

## 13. Build scope

In scope for the build window: the factorisation model, adaptive selection, coordination detection, the live voting interface, the opinion map, the consensus certificate, one generation loop, jurisdiction routing over a subset of the Allocation of Business Rules, one filing channel with a sandboxed adapter, the escalation scheduler with a compressible clock, and the ledger.

Out of scope: real government integration, authentication and identity, multilingual coverage beyond two languages in the seed corpus, mobile applications, and any live filing.

## 14. Glossary

- **Bridging score**: the statement intercept `mu(j)`, meaning agreement remaining after factional variance is explained.
- **Fault line**: a statement with low intercept and high factor loading, so it matters and it divides.
- **Consensus certificate**: the support figures inside every detected faction attached to a drafted clause.
- **Generation loop**: proposing reformulations of fault lines, measuring their agreement, and keeping the winners.
- **Allocation of Business Rules**: the published instrument assigning subjects to ministries, used here as routing ground truth.
- **Ledger**: the append-only public record of autonomous actions.
