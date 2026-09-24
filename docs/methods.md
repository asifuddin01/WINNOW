# Methods note: relevance ranking, the stopping helper, and AI suggestions

This describes what Winnow does, in words a review team can adapt for the methods section
of a protocol or report. Numbers refer to the build guide's sections.

## Relevance ranking (active learning)

Winnow orders the title-and-abstract queue by how likely each record is to be relevant,
learning from the review team's own decisions on the Winnow server; no record leaves it.

- **Features.** Each record is represented by TF-IDF weights over word unigrams and
  bigrams of its title (counted twice), abstract and keywords, with sublinear term
  frequency, words in at least two records, and at most 100,000 features. The vocabulary
  is built from all the review's records.
- **Model.** L2-regularised logistic regression (C = 1, class-balanced weights, liblinear),
  scikit-learn 1.9.
- **Labels.** A record's final title-and-abstract status: included or maybe count as
  relevant, excluded as not. A record not yet final takes the majority of the individual
  decisions on it; a tie is left out.
- **When it trains.** The first model once the review has 5 relevant and 5 excluded
  records; before that the queue is in random order. It retrains after every 25 new
  decisions, at most once a minute, and on request.
- **Scores.** Every record still waiting at the stage is scored with the model's
  probability of relevance. A record that has already been decided by someone but is still
  waiting for another reviewer is scored by cross-fitting — by a model trained without it —
  so its position never reflects the decision already made on it (this matters under blind
  screening). The same out-of-fold scores give the reported cross-validated AUC, from 50
  labelled records.
- **Exploration.** In relevance order, one record in every 20 served is taken from the
  reviewer's random order instead, so the model keeps learning about records it would rank
  low.

On 21 labelled reviews from the SYNERGY collection, this ordering found 95% of the
includes after a median of 55% fewer records than random order (range 13–85%); see
[the benchmark](ranking-benchmark.md).

## The stopping helper

Winnow never stops screening. When a reviewer has excluded a set number of records in a
row (200 by default, set per review), it says so and estimates how many relevant records
remain among those they have not screened.

The estimate models the rate at which the reviewer's decisions have found relevant records
as a Poisson process whose intensity decays exponentially with the number of records
screened, fitted by maximum likelihood, and sums the fitted intensity over the records
left. Only decisions made in relevance order count; those made in random order before the
first model are left out. It is fitted twice, to those decisions and to their more recent
half (at least 200); each fit's 90% range comes from a parametric bootstrap (200
resamples), the reported range spans both and its top is widened by two Poisson standard
deviations, and the headline is the larger of the two point estimates. On the benchmark
runs the range contained the true number left 96% of the time and fell short of it 4% of
the time; the headline was off by 0.8 records at the median.

It assumes relevant records keep getting rarer as screening goes on. It is less reliable
when the search or the criteria changed during screening, and early on, when the model has
had little to learn from. A review should report the stopping criterion it chose, not the
helper's estimate alone.

## AI suggestions (optional, off by default)

When an instance administrator has configured a provider and the review's owner has
turned the feature on, a reviewer can ask for a suggestion on one record. Winnow sends the
record's title, abstract, keywords, year, journal and publication type, with the review's
title, question, PICO and numbered criteria, to the provider, and asks for a suggested
decision (include, exclude or maybe), a verdict on each criterion (met, not met,
unclear), a confidence and a short rationale, under a fixed JSON schema. The prompt tells
the model to treat the record as data, not instructions.

- **Providers.** Anthropic (Claude Opus 5 by default, `claude-opus-5`, with structured
  output, low effort and the API's refusal fallback) or a local or self-hosted model
  behind an OpenAI-compatible endpoint.
- **Nothing is decided by the AI.** A suggestion is shown beside the record; the reviewer
  decides. Suggestions are private to the person who asked while screening.
- **Everything is kept.** Each suggestion is stored with the provider, the model, the
  prompt version and the time. The review's owners and admins can download all of them,
  with each reviewer's own decision beside the suggestion, to report AI use in the
  methods (for example, following the relevant reporting guidance on automation tools).
