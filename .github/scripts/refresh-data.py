#!/usr/bin/env python3
"""
Trivium DSP data refresh — GitHub Actions runtime.

Called by .github/workflows/refresh-data.yml on a weekly cron.
Hits /gmail-ingest to pull any new Amazon Ads report emails into Netlify
Blobs, fetches the latest CSV for this repo's client via /data-export,
aggregates per-(date × campaign × ad group × ad) → per-day summary in
the 22-column TheraIce parser format the dashboard expects, and writes
to public/data/dsp.csv. The workflow YAML handles git commit + push.

Env vars (set in workflow):
  AUTH_ADMIN_TOKEN   bearer token gating the Trivium auth site admin endpoints
  CLIENT_SLUG        client slug (e.g., "mirai-clinical")
  DATA_SLOT          dataset slot (e.g., "dsp")
"""

import os
import sys
import csv
import json
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

# ── Configuration ────────────────────────────────────────────

AUTH_BASE = "https://trivium-amazon-ads-auth.netlify.app"
AUTH_TOKEN = os.environ.get("AUTH_ADMIN_TOKEN")
CLIENT_SLUG = os.environ.get("CLIENT_SLUG", "mirai-clinical")
DATA_SLOT = os.environ.get("DATA_SLOT", "dsp")

OUT_PATH = Path("public/data/dsp.csv")

if not AUTH_TOKEN:
    sys.exit("ERR: AUTH_ADMIN_TOKEN not set. Add it as a GitHub repo secret.")

# ── HTTP helpers ─────────────────────────────────────────────

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if hasattr(e, "read") else b""

def auth_headers():
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}

# ── Aggregation ──────────────────────────────────────────────

def num(s):
    if s is None:
        return 0.0
    s = str(s).replace("=", "").replace('"', "").replace("%", "").replace(",", "").strip()
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0

def aggregate_dsp(raw_csv):
    """
    Per-(date × campaign × ad group × ad) granular Amazon DSP CSV
    → per-day summary in 22-column TheraIce parser format.
    """
    rows = list(csv.DictReader(StringIO(raw_csv)))
    if not rows:
        raise ValueError("Empty CSV")

    by_date = defaultdict(lambda: defaultdict(float))
    brand = ""
    brand_id = 0.0

    for r in rows:
        d = r["Date"].strip()
        if not brand:
            brand = r.get("Advertiser account name", "").strip()
            brand_id = num(r.get("Advertiser account ID", ""))
        by_date[d]["spend"]               += num(r.get("Total cost"))
        by_date[d]["impressions"]         += num(r.get("Impressions"))
        by_date[d]["clicks"]              += num(r.get("Click-throughs"))
        by_date[d]["dpv"]                 += num(r.get("DPV"))
        by_date[d]["atc"]                 += num(r.get("ATC"))
        by_date[d]["purchases"]           += num(r.get("Purchases"))
        by_date[d]["ntb_purchases"]       += num(r.get("New-to-brand purchases"))
        by_date[d]["sales"]               += num(r.get("Sales USD"))
        by_date[d]["total_dpv"]           += num(r.get("Total DPV"))
        by_date[d]["total_atc"]           += num(r.get("Total ATC"))
        by_date[d]["total_purchases"]     += num(r.get("Total purchases"))
        by_date[d]["total_ntb_purchases"] += num(r.get("Total new-to-brand purchases"))
        by_date[d]["total_sales"]         += num(r.get("Total sales USD"))
        by_date[d]["total_ntb_sales"]     += num(r.get("Total new-to-brand product sales USD"))

    dates = sorted(by_date.keys(), key=lambda d: datetime.strptime(d, "%b %d, %Y"))

    HEADER = [
        "Date", "Advertiser account name", "Advertiser account ID",
        "Total cost", "Impressions", "CTR", "DPV", "ATC",
        "Purchases", "New-to-brand purchases", "Percent of purchases new-to-brand",
        "Sales USD", "New-to-brand product sales USD",
        "Total DPV", "Total ATC", "Total purchases", "Total new-to-brand purchases",
        "Total new-to-brand purchases clicks",
        "Total percent of purchases new-to-brand", "Total sales USD",
        "Total ROAS", "Total new-to-brand product sales USD",
    ]

    out = StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_ALL)
    w.writerow(HEADER)
    for d in dates:
        a = by_date[d]
        ctr_pct       = (a["clicks"] / a["impressions"] * 100) if a["impressions"] else 0
        ntb_pct       = (a["ntb_purchases"] / a["purchases"] * 100) if a["purchases"] else 0
        total_ntb_pct = (a["total_ntb_purchases"] / a["total_purchases"] * 100) if a["total_purchases"] else 0
        total_roas    = (a["total_sales"] / a["spend"]) if a["spend"] else 0
        w.writerow([
            d, brand, f'="{int(brand_id)}"',
            f"{a['spend']:.5f}", int(a["impressions"]), f"{ctr_pct:.4f}%",
            int(a["dpv"]), int(a["atc"]),
            int(a["purchases"]), int(a["ntb_purchases"]), f"{ntb_pct:.4f}%",
            f"{a['sales']:.5f}", "0.00000",
            int(a["total_dpv"]), int(a["total_atc"]),
            int(a["total_purchases"]), int(a["total_ntb_purchases"]), 0,
            f"{total_ntb_pct:.4f}%", f"{a['total_sales']:.5f}",
            f"{total_roas:.5f}", f"{a['total_ntb_sales']:.5f}",
        ])
    return out.getvalue(), len(dates)

# ── Main ─────────────────────────────────────────────────────

def main():
    print(f"=== Trivium DSP refresh @ {datetime.now(timezone.utc).isoformat()} ===")
    print(f"  client = {CLIENT_SLUG}")
    print(f"  slot   = {DATA_SLOT}")
    print()

    # 1. Trigger /gmail-ingest to pull any new Amazon Ads emails into Netlify Blobs
    print(f"[ingest] calling {AUTH_BASE}/gmail-ingest?lookback_days=14")
    status, _, body = http_get(f"{AUTH_BASE}/gmail-ingest?lookback_days=14", auth_headers())
    if status != 200:
        print(f"  ✗ FAILED {status}: {body[:500]!r}")
        sys.exit(1)
    data = json.loads(body)
    print(
        f"  ✓ found={data.get('found', 0)} "
        f"processed={len(data.get('processed', []))} "
        f"skipped={len(data.get('skipped', []))} "
        f"errors={len(data.get('errors', []))}"
    )
    for err in data.get("errors", []):
        print(f"    ! ingest error: {err}")

    # 2. Fetch latest CSV for this client
    print(f"\n[data-export] fetching latest {CLIENT_SLUG}/{DATA_SLOT} CSV")
    url = f"{AUTH_BASE}/data-export?client={CLIENT_SLUG}&slot={DATA_SLOT}&latest=true"
    status, headers, body = http_get(url, auth_headers())
    if status != 200:
        print(f"  ✗ FAILED {status}: {body[:500]!r}")
        sys.exit(1)
    captured = headers.get("x-captured-at") or headers.get("X-Captured-At") or "unknown"
    subject = headers.get("x-subject") or headers.get("X-Subject") or ""
    print(f"  ✓ {len(body)} bytes")
    print(f"    captured: {captured}")
    print(f"    subject:  {subject}")

    # 3. Aggregate per-(date × campaign × ad group × ad) → per-day summary
    print(f"\n[aggregate] rolling up to daily summary")
    agg_csv, ndays = aggregate_dsp(body.decode("utf-8"))
    print(f"  ✓ {ndays} daily rows, {len(agg_csv)} bytes")

    # 4. Write to disk (workflow YAML handles git commit + push)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(agg_csv)
    print(f"\n[write] {OUT_PATH} updated")
    print(f"\n=== Done ===")

if __name__ == "__main__":
    main()
