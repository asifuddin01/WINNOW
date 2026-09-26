// Guide 13's load test: reviewers screening at once, each deciding every 3 seconds.
// Run it with `make load`, which prepares the accounts and review (benchmarks/load_setup.py)
// and removes them afterwards. Every reviewer asks for the next records and decides the
// first, as the screen does, through Caddy, as browsers reach it.
import { check } from "k6";
import http from "k6/http";

const setup = JSON.parse(open("/load/load.json"));
const base = __ENV.BASE_URL || "http://caddy:8080";
const api = `${base}/api/v1/projects/${setup.project}`;

// A trial of the production stack on one machine (docs/deploy.md): its Caddy answers only to
// SITE_ADDRESS with a local certificate, so point that name at Caddy and trust the cert.
const siteHost = base.split("://")[1].split(/[:/]/)[0];

export const options = {
  hosts: __ENV.TARGET_IP ? { [siteHost]: __ENV.TARGET_IP } : {},
  insecureSkipTLSVerify: __ENV.INSECURE_TLS === "1",
  // Each reviewer decides every 3 seconds on average, independently: one iteration every
  // 3 s per reviewer, spread over time. (With a constant number of looping VUs they would
  // all click in the same instant, forever: waves of 50 requests and then silence.)
  scenarios: {
    reviewers: {
      executor: "constant-arrival-rate",
      rate: setup.reviewers.length,
      timeUnit: "3s",
      duration: __ENV.DURATION || "10m",
      preAllocatedVUs: setup.reviewers.length,
      maxVUs: setup.reviewers.length,
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
}
