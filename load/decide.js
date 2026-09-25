// Guide 13's load test: reviewers screening at once, each deciding every 3 seconds.
// Run it with `make load`, which prepares the accounts and review (benchmarks/load_setup.py)
// and removes them afterwards. Every reviewer asks for the next records and decides the
// first, as the screen does, through Caddy, as browsers reach it.
import { check, sleep } from "k6";
import http from "k6/http";

const setup = JSON.parse(open("/load/load.json"));
const base = __ENV.BASE_URL || "http://caddy:8080";
const api = `${base}/api/v1/projects/${setup.project}`;

export const options = {
  scenarios: {
    reviewers: {
      executor: "constant-vus",
      vus: setup.reviewers.length,
      duration: __ENV.DURATION || "10m",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<100"],
    http_req_failed: ["rate<0.001"],
  },
};

export default function () {
  const me = setup.reviewers[(__VU - 1) % setup.reviewers.length];
  const headers = { Cookie: me.cookie, Origin: setup.origin, "X-CSRF-Token": me.csrf };

  const queue = http.get(`${api}/screening/queue?stage=title_abstract&n=10`, {
    headers,
    tags: { name: "next records" },
  });
  check(queue, { "next records": (r) => r.status === 200 });
  const next = queue.status === 200 ? queue.json("items")[0] : undefined;
  if (next) {
    const decided = http.put(
      `${api}/records/${next.id}/decision`,
      JSON.stringify({ stage: "title_abstract", decision: Math.random() < 0.3 ? "include" : "exclude" }),
      { headers: { ...headers, "Content-Type": "application/json" }, tags: { name: "decision" } },
    );
    check(decided, { decision: (r) => r.status === 200 });
  }
  sleep(3);
}
