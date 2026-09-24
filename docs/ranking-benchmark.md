# Relevance ranking: benchmark (Phase 6 acceptance)

**Question (guide, Phase 6):** on public labelled systematic reviews, does relevance
ordering find 95% of the includes after screening substantially fewer records than random
order?

**Answer:** yes. Over 21 reviews from the SYNERGY collection, screening in Winnow's
relevance order found 95% of the includes after a median **63% fewer records** than random
order needs on average (range 14–91%). Pooled over all 21, it took **15,771 records
instead of 55,658 (72% fewer)**. The median share of a review screened to reach 95% recall
was 35%.

Under guide 8.10's original rule — no model until 5 includes and 5 excludes — the same
reviews saved a median 55% (pooled 62%). On this evidence the owner chose to train the first
model from the first include and exclude (2026-09-25); the numbers below are for that.

## What was run

- **Data.** SYNERGY (asreview/synergy-dataset, CC0): 21 of its reviews with OpenAlex ids,
  59,135 records, 1,987 of them included by the reviews' authors. Titles, abstracts and
  keywords come from the OpenAlex API, as SYNERGY's own tool fetches them. Two reviews
  (Nagtegaal 2019, Moran 2021) publish no OpenAlex ids and one (Brouwer 2019, 46k records)
  did not fit the day's OpenAlex allowance; they are not included. Some records per review
  are missing from OpenAlex (at most 48, in van de Schoot 2018).
- **Code.** The product's own ranking (`app/ranking`), replayed as one reviewer screening
  each review, exactly as the queue serves it:
  - random order until there is one include and one exclude;
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
The last column is the saving had the first model waited for five includes and five
excludes, as guide 8.10 first had it.

| Review | Records | Includes | Relevance order | Random order | Fewer records | WSS@95 | Waiting for 5 + 5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Donners 2021 | 253 | 15 | 111 | 238 | 53% | 51.1% | 57% |
| Sep 2021 | 271 | 40 | 216 | 252 | 14% | 15.3% | 13% |
| Muthu 2022 | 283 | 6 | 139 | 243 | 43% | 45.9% | 13% |
| van der Valk 2021 | 723 | 89 | 389 | 684 | 43% | 41.2% | 43% |
| Meijboom 2021 | 881 | 37 | 210 | 836 | 75% | 71.2% | 63% |
| Oud 2018 | 950 | 20 | 250 | 860 | 71% | 68.7% | 54% |
| Menon 2022 | 973 | 73 | 427 | 921 | 54% | 51.1% | 54% |
| Jeyaraman 2020 | 1,172 | 96 | 503 | 1,113 | 55% | 52.1% | 51% |
| Bannach-Brown 2019 | 1,927 | 265 | 688 | 1,827 | 62% | 59.3% | 62% |
| van der Waal 2022 | 1,962 | 33 | 690 | 1,848 | 63% | 59.8% | 50% |
| Kwok 2020 | 2,240 | 118 | 944 | 2,128 | 56% | 52.9% | 55% |
| Smid 2020 | 2,591 | 27 | 465 | 2,407 | 81% | 77.1% | 72% |
| Muthu 2021 | 2,718 | 336 | 1,610 | 2,582 | 38% | 35.8% | 38% |
| Appenzeller-Herzog 2019 | 2,851 | 26 | 1,083 | 2,641 | 59% | 57.0% | 54% |
| Welling 2021 | 3,647 | 71 | 638 | 3,445 | 81% | 77.5% | 79% |
| Wolters 2018 | 4,260 | 19 | 758 | 4,048 | 81% | 77.2% | 60% |
| van de Schoot 2018 | 4,496 | 38 | 432 | 4,266 | 90% | 85.4% | 85% |
| Bos 2018 | 4,866 | 10 | 699 | 4,425 | 84% | 80.6% | 48% |
| Leenaars 2019 | 5,791 | 17 | 497 | 5,470 | 91% | 86.4% | 64% |
| Leenaars 2020 | 7,186 | 579 | 2,143 | 6,828 | 69% | 65.2% | 68% |
| van Dis 2020 | 9,094 | 72 | 2,879 | 8,597 | 67% | 63.3% | 62% |

## What the comparisons show

- **Exploration costs nothing measurable.** Measured under the 5 + 5 rule: without the
  one-in-twenty random records the median saving was the same 55% (pooled 62%).
- **Waiting for five includes was the largest cost, on sparse reviews.** Before the first
  model the queue is in random order, and when a review includes a fraction of a percent of
  its records, finding five at random is most of the work: Bos 2018 (10 includes in 4,866)
  needed 2,291 records under the 5 + 5 rule and needs 699 now; Leenaars 2019 (17 in 5,791)
  1,966 against 497. On reviews with many includes it makes no difference (Leenaars 2020:
  69% against 68%), and on the smallest one it was slightly worse (Donners 2021: 53%
  against 57%).
- **Very small reviews gain little.** With under 300 records and a retrain every 25
  decisions, the model is retrained only a handful of times before the review is done
  (Sep 2021, Muthu 2022).

## The stopping-rule helper

At the point where the reviewer has excluded 200 records in a row (the default rule), the
helper estimates how many relevant records are left (see [methods](methods.md)). Replayed
on the same runs:

- the rule spoke up in 90 of 105 runs; recall at that moment was 97.2% at the median and
  at least 95% in 73 of them, but as low as 66.7%;
- the true number left was inside the helper's range in 89 of 90 cases (99%) and above it
  in 1; the headline number was off by 0.9 records at the median. Two earlier versions
  were measured (under the 5 + 5 rule) and replaced: fitting only the recent half of the
  history held the truth in 72% of cases and fell short in 20%; adding the whole history
  raised that to 87%, but the
  random warm-up before the first model made the headline far too high (a reviewer who had
  found every include was told "about 25 left"). The helper now fits only the decisions
  made in relevance order, twice, and widens the top of the range.

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
