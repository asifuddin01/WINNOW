# Relevance ranking: benchmark (Phase 6 acceptance)

**Question (guide, Phase 6):** on public labelled systematic reviews, does relevance
ordering find 95% of the includes after screening substantially fewer records than random
order?

**Answer:** yes. Over 21 reviews from the SYNERGY collection, screening in Winnow's
relevance order found 95% of the includes after a median **55% fewer records** than random
order needs on average (range 13–85%). Pooled over all 21, it took **21,296 records
instead of 55,658 (62% fewer)**. The median share of a review screened to reach 95% recall
was 42%.

## What was run

- **Data.** SYNERGY (asreview/synergy-dataset, CC0): 21 of its reviews with OpenAlex ids,
  59,135 records, 1,987 of them included by the reviews' authors. Titles, abstracts and
  keywords come from the OpenAlex API, as SYNERGY's own tool fetches them. Two reviews
  (Nagtegaal 2019, Moran 2021) publish no OpenAlex ids and one (Brouwer 2019, 46k records)
  did not fit the day's OpenAlex allowance; they are not included. Some records per review
  are missing from OpenAlex (at most 48, in van de Schoot 2018).
- **Code.** The product's own ranking (`app/ranking`), replayed as one reviewer screening
  each review, exactly as the queue serves it:
  - random order until there are 5 includes and 5 excludes (guide 8.10);
  - then relevance order, retrained after every 25 decisions (guide 8.10);
  - one record in 20 from random order instead (guide 9.2's exploration).
- **Random order** is not simulated: the expected number of records before the k-th of I
  includes among N, in a random order, is k(N+1)/(I+1).
- **Five runs per review** (different random warm-ups); the table gives the median.
- **WSS@95** (work saved over sampling at 95% recall) = (N − screened)/N − 0.05.

Reproduce (the data is fetched, never committed):

```bash
docker compose exec api python benchmarks/synergy.py <review names…>
docker compose exec api python -m benchmarks.ranking --runs 5 --compare
docker compose exec api python -m benchmarks.stopping
```

## Results, by review

"Relevance order" and "Random order" are records screened to find 95% of the includes.
The last column is the same measure had the first model been trained from the first
include and the first exclude, instead of waiting for five of each (see below).

| Review | Records | Includes | Relevance order | Random order | Fewer records | WSS@95 | From the first include |
|---|---:|---:|---:|---:|---:|---:|---:|
| Donners 2021 | 253 | 15 | 103 | 238 | 57% | 54.3% | 53% |
| Sep 2021 | 271 | 40 | 220 | 252 | 13% | 13.8% | 14% |
| Muthu 2022 | 283 | 6 | 212 | 243 | 13% | 20.1% | 43% |
| van der Valk 2021 | 723 | 89 | 391 | 684 | 43% | 40.9% | 43% |
| Meijboom 2021 | 881 | 37 | 306 | 836 | 63% | 60.3% | 75% |
| Oud 2018 | 950 | 20 | 396 | 860 | 54% | 53.3% | 71% |
| Menon 2022 | 973 | 73 | 427 | 921 | 54% | 51.1% | 54% |
| Jeyaraman 2020 | 1,172 | 96 | 548 | 1,113 | 51% | 48.2% | 55% |
| Bannach-Brown 2019 | 1,927 | 265 | 693 | 1,827 | 62% | 59.0% | 62% |
| van der Waal 2022 | 1,962 | 33 | 915 | 1,848 | 50% | 48.4% | 63% |
| Kwok 2020 | 2,240 | 118 | 958 | 2,128 | 55% | 52.2% | 56% |
| Smid 2020 | 2,591 | 27 | 674 | 2,407 | 72% | 69.0% | 81% |
| Muthu 2021 | 2,718 | 336 | 1,604 | 2,582 | 38% | 36.0% | 38% |
| Appenzeller-Herzog 2019 | 2,851 | 26 | 1,219 | 2,641 | 54% | 52.2% | 59% |
| Welling 2021 | 3,647 | 71 | 736 | 3,445 | 79% | 74.8% | 81% |
| Wolters 2018 | 4,260 | 19 | 1,612 | 4,048 | 60% | 57.2% | 81% |
| van de Schoot 2018 | 4,496 | 38 | 626 | 4,266 | 85% | 81.1% | 90% |
| Bos 2018 | 4,866 | 10 | 2,291 | 4,425 | 48% | 47.9% | 84% |
| Leenaars 2019 | 5,791 | 17 | 1,966 | 5,470 | 64% | 61.1% | 91% |
| Leenaars 2020 | 7,186 | 579 | 2,175 | 6,828 | 68% | 64.7% | 69% |
| van Dis 2020 | 9,094 | 72 | 3,224 | 8,597 | 62% | 59.5% | 67% |

## What the comparisons show

- **Exploration costs nothing measurable.** Without the one-in-twenty random records the
  median saving is the same 55% (pooled 62%).
- **Waiting for five includes is the largest cost, on sparse reviews.** Before the first
  model the queue is in random order, and when a review includes a fraction of a percent of
  its records, finding five at random is most of the work: Bos 2018 (10 includes in 4,866)
  needs 2,291 records under the guide's rule and 699 when the first model is trained from
  the first include and exclude; Leenaars 2019 (17 in 5,791) 1,966 against 497. Across all
  21 the median saving would be 63% (pooled 72%) instead of 55% (62%). Winnow follows the
  guide's 5 + 5 rule; lowering it is a one-line change (`MIN_EACH` in
  `app/ranking/model.py`) left to the owner's decision.
- **Very small reviews gain little.** With under 300 records and a retrain every 25
  decisions, the model is retrained only a handful of times before the review is done
  (Sep 2021, Muthu 2022).

## The stopping-rule helper

At the point where the reviewer has excluded 200 records in a row (the default rule), the
helper estimates how many relevant records are left (see [methods](methods.md)). Replayed
on the same runs:

- the rule spoke up in 90 of 105 runs; recall at that moment was 98.8% at the median and
  at least 95% in 73 of them, but as low as 70.8% (in one run on van Dis 2020);
- the true number left was inside the helper's range in 78 of 90 cases (87%), above it in
  5 (6%), below it in 7. Fitting only the recent half of the history, as a first version
  did, held it in 72% and fell short in 20%; the helper now fits both and spans both.

It is advice: a long run of excludes is common evidence for stopping, not proof, and the
screen says so.

## Speed (guide 9.2: 50,000 records in under 10 seconds)

`python -m benchmarks.ranking_speed`: the ranking job on 50,000 real abstracts with 2,000
decisions, in the test database, database reads and writes included.

| Run | Time | Where it goes |
|---|---:|---|
| First, building the review's TF-IDF corpus | 32–55 s | corpus 27–50 s (once per import, in the worker) |
| Later runs (corpus cached) | 3.9–5.1 s (one run 8.4 s) | labels 0.7 s, training and scoring 1.4–2.2 s, writing scores 1.6–2.6 s |

The queue's next ten records in relevance order: 17 ms median, 24 ms p95. Writing the
scores onto `records` took 13–17 s of a 19 s run (every write rewrote the row's ten
indexes); they now live in `record_scores`.
