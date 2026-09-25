"""The OWASP ZAP baseline passes when it raises no high-risk alert (guide 12, Phase 9).

Reads ZAP's JSON report, prints every alert (as a GitHub annotation, which can be read
without signing in to GitHub) and exits 1 on any high-risk one.

    python3 security/zap_verdict.py zap-report/zap.json
"""

import json
import sys
from pathlib import Path

RISK = {"0": "informational", "1": "low", "2": "medium", "3": "high"}
LEVEL = {"3": "error", "2": "warning"}


def main(path: str) -> int:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    alerts = [alert for site in report.get("site", []) for alert in site.get("alerts", [])]
    alerts.sort(key=lambda alert: -int(alert["riskcode"]))
    for alert in alerts:
        risk = alert["riskcode"]
        where = [instance["uri"] for instance in alert.get("instances", [])]
        example = f", e.g. {where[0]}" if where else ""
        print(
            f"::{LEVEL.get(risk, 'notice')} title=ZAP {RISK[risk]}: {alert['name']}::"
            f"rule {alert['pluginid']} on {len(where)} URL(s){example}"
        )
    high = [alert for alert in alerts if alert["riskcode"] == "3"]
    counts = {name: sum(a["riskcode"] == code for a in alerts) for code, name in RISK.items()}
    print(f"ZAP baseline: {counts}. High-risk alerts: {len(high)}.")
    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
