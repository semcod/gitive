# The model

## What "intuition" means here

Deliberation is expensive: enumerating every possible piece of work and evaluating each
against the project's goal. Intuition is the cheap policy $q_\theta(c \mid \mathcal{F})$
that approximates the outcome of that search without running it — amortized inference.
The LLM supplies candidates (the expensive, generative half); $q_\theta$ ranks them (the
cheap, learned half). Splitting the two is what makes $\theta$ learnable: if the LLM also
picked, there would be no separable decision to attribute an outcome to.

## Facts

A fact is an immutable observation $f_i = (t_i, k_i, \text{text}_i)$ with embedding
$e_i \in \mathbb{R}^d$, $\|e_i\| = 1$. Facts split into two families:

| family | kinds | goes into |
|---|---|---|
| achievement | `commit`, `pr_merged`, `issue_closed`, `ci_success` | $s_t$ |
| friction | `ci_failure`, `revert`, `marker` | $r_t$ |

Keeping them apart matters. Folding a red pipeline into $s_t$ would make the model treat
the failure as accomplished work, and the tension vector would point away from the very
thing that is broken.

## Memory kernel

$$w_i = \kappa_{k_i} \cdot \exp\!\left(-\ln 2 \cdot \frac{t - t_i}{h}\right)$$

$h$ is the half-life (default 14 days). $\kappa$ is a per-kind prior: `ci_failure` = 2.5,
`commit` = 1.0, `ci_success` = 0.4 — a green build is weak evidence about direction, a red
one is strong. Friction uses $h/2$, because a failure from a month ago is usually gone.

$$s_t = \widehat{\sum_{i \in \text{ach}} w_i e_i}, \qquad
  r_t = \widehat{\sum_{i \in \text{fri}} w_i e_i}$$

($\widehat{\cdot}$ denotes L2 normalisation.)

## Tension

$$\tilde{\delta_t} = \underbrace{\big(g - \langle g, s_t\rangle s_t\big)}_{\text{unmet goal}} + \mu\, r_t,
\qquad \delta_t = \widehat{\tilde{\delta_t}}$$

The first term is the component of the goal orthogonal to what has already been achieved —
formally, "what is missing". The second bends that direction toward whatever is currently
breaking, with $\mu$ controlling how much a failing pipeline is allowed to preempt the
roadmap. $\|\tilde{\delta_t}\|$ is retained separately: normalisation destroys exactly the
quantity the convergence test needs.

## Scoring

For each candidate $c$ with embedding $e_c$ and self-declared cost $\hat{k}(c) \in [1,5]$:

$$\phi(c) = \begin{bmatrix}
\langle e_c, \delta_t \rangle \\
(1 - \langle e_c, s_t \rangle)\cdot \mathbb{1}[\langle e_c, \delta_t\rangle > \alpha_0] \\
\hat{k}(c)/5 \\
\max_{c' \in \mathcal{D}} \langle e_c, e_{c'} \rangle
\end{bmatrix}
\quad
U_\theta(c) = \theta^\top \phi(c)
\quad
\theta_0 = \begin{bmatrix} 1.0 \\ 0.3 \\ -0.2 \\ -0.6 \end{bmatrix}$$

The indicator is the important part. An ungated surprise term maximises at candidates
orthogonal to everything — i.e. work unrelated to the project. Gating it behind an
alignment floor $\alpha_0$ means novelty is only rewarded *within* the relevant subspace.

$$p(c) = \frac{\exp(U_\theta(c)/\tau)}{\sum_j \exp(U_\theta(c_j)/\tau)}$$

$\tau$ is the explore/exploit dial: $\tau \to 0$ doggedly finishes one thread, large $\tau$
scatters attention. The top-$k$ by $U$ are opened as issues; $p$ is recorded for analysis
and for switching to sampling if you prefer stochastic selection.

## Learning

GitHub supplies the label for free, with no human in the loop beyond normal work:

$$y = \begin{cases}
1 & \text{issue closed as completed within } H \text{ days} \\
0 & \text{closed as not-planned/duplicate, or still open past } H
\end{cases}$$

$$\theta \leftarrow \theta + \eta\,\big(y - \sigma(\theta^\top\phi)\big)\,\phi$$

Online logistic regression on four features. It converges fast because $d = 4$, and
`weights.json` is committed each cycle, so `git log -p .intuition/weights.json` is a
readable history of how the system's judgement changed.

## Convergence and goal renewal

When $\|\tilde{\delta_t}\|$ is both small and flat over a window of cycles, the goal has
been met. The loop then asks the LLM to restate $g$ from the README plus recent activity,
increments `generation`, and continues. This is what makes the loop genuinely unbounded
rather than merely long-running: the objective itself is part of the state.

## Failure modes to watch

| symptom | cause | fix |
|---|---|---|
| proposals drift off-project | `align_floor` too low, or lexical embedder confusing subjects | raise `INTUITION_ALIGN_FLOOR`, set a real `INTUITION_EMBED_MODEL` |
| same task reproposed in new words | redundancy is cosine-based; a rephrase escapes it | lower $\tau$, raise \|θ_redundancy\|, keep closed issues labelled |
| loop obsesses over one flaky test | `ci_failure` weight × short half-life amplifies a repeated failure | quarantine the flake, or lower `INTUITION_FRICTION_WEIGHT` |
| $\theta$ collapses toward zero | most issues are neither closed nor labelled, so $y=0$ dominates | shorten `INTUITION_HORIZON_DAYS`, or close stale issues as not-planned |
| tension never converges | the goal is aspirational rather than technical | write a concrete `GOAL.md`; it takes precedence over README |
