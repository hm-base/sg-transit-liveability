"""
scripts/publish_static_page.py
================================
Generate a static, self-contained snapshot page from the LIVE local API
(http://localhost:8000) and push it into a separate portfolio-site repo for
GitHub Pages. Unlike the interactive Streamlit dashboard, this page has real
numbers baked in at generation time — no client-side fetch() calls — so it
actually works on GitHub Pages (which has no backend to call).

This is a SNAPSHOT, not a live feed: it only updates when you run this
script again. The page makes that unmistakable with a persistent banner and
a one-time modal, both showing the real generation timestamp.

Usage:
    # 1. python main.py   (running locally, so the API below has real data)
    # 2. python scripts/publish_static_page.py --site-repo <path or URL>

    python scripts/publish_static_page.py \
        --site-repo https://github.com/hm-base/Goh-Hui-Min-site.git

Requires: the local pipeline running (python main.py) so localhost:8000 has
real data, and push access to the target site repo.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SGT = timezone(timedelta(hours=8))
API_BASE = "http://localhost:8000"
PAGE_SUBPATH = "public/sg-transit/index.html"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True):
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if check and result.returncode != 0 and result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result


def fetch_json(path: str, **params):
    r = requests.get(f"{API_BASE}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def verdict_class(score: float) -> str:
    if score >= 65:
        return "bg-emerald-50 text-emerald-700 border-emerald-200"
    if score >= 45:
        return "bg-amber-50 text-amber-700 border-amber-200"
    return "bg-rose-50 text-rose-700 border-rose-200"


def rank_table(rows: list[dict], score_key: str, verdict_key: str, extra_cols: list[tuple[str, str]]) -> str:
    head_extra = "".join(f"<th class='text-left py-2 px-3 font-semibold text-[#0F172A]/60'>{h}</th>" for h, _ in extra_cols)
    body = ""
    for i, r in enumerate(rows[:10], 1):
        cells = "".join(f"<td class='py-2 px-3'>{r.get(k, '—')}</td>" for _, k in extra_cols)
        body += f"""<tr class="border-t border-[#DDD6FE]/30">
          <td class="py-2 px-3 text-[#0F172A]/50">{i}</td>
          <td class="py-2 px-3 font-semibold">{r['district'] if 'district' in r else r['town']}</td>
          <td class="py-2 px-3">
            <span class="inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold border {verdict_class(r[score_key])}">
              {r[score_key]:.1f}
            </span>
          </td>
          {cells}
        </tr>"""
    return f"""<table class="w-full text-sm">
      <thead><tr class="text-left">
        <th class="py-2 px-3 font-semibold text-[#0F172A]/60">#</th>
        <th class="py-2 px-3 font-semibold text-[#0F172A]/60">Town / District</th>
        <th class="py-2 px-3 font-semibold text-[#0F172A]/60">Score</th>
        {head_extra}
      </tr></thead>
      <tbody>{body}</tbody>
    </table>"""


def build_page(rank_data: list[dict], vfm_data: list[dict], generated_at: str) -> str:
    n_districts = len(rank_data)
    avg_conn = sum(r["score"] for r in rank_data) / n_districts if n_districts else 0
    avg_vfm = sum(r["vfm_score"] for r in vfm_data) / len(vfm_data) if vfm_data else 0

    # bus score needs formatting -> pre-format into a display key first
    for r in rank_data:
        bf = r.get("bus_frequency_score")
        r["bus_frequency_score_display"] = f"{bf:.0f}/100" if bf is not None else "—"
    leaderboard_html = rank_table(rank_data, "score", "verdict", [
        ("Bus Score", "bus_frequency_score_display"),
    ]) if rank_data else "<p class='text-sm text-[#0F172A]/50'>No data available.</p>"

    for r in vfm_data:
        r["avg_price_display"] = f"S${r['avg_price']:,.0f}" if r.get("avg_price") is not None else "—"
    vfm_html = rank_table(vfm_data, "vfm_score", "vfm_verdict", [
        ("Avg Price", "avg_price_display"),
    ]) if vfm_data else "<p class='text-sm text-[#0F172A]/50'>No data available.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SG Transit Liveability — Demo Snapshot</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>body{{font-family:'Inter',sans-serif;}}</style>
</head>
<body class="bg-[#F8FAFC] text-[#0F172A] antialiased">

<!-- Persistent "not live" banner -->
<div class="bg-amber-50 border-b border-amber-200 text-amber-800 text-sm text-center py-2 px-4">
  📸 Static demo snapshot — not a live feed · Data frozen at generation time · Last updated:
  <strong>{generated_at}</strong>
</div>

<!-- One-time modal -->
<div id="snapshot-modal" class="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4 hidden">
  <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl">
    <h3 class="font-bold text-lg mb-2">This is a snapshot, not a live page</h3>
    <p class="text-sm text-[#0F172A]/65 leading-relaxed mb-4">
      SG Transit Liveability Index is a real-time data pipeline (live taxi/bus polling,
      ML forecasting, anomaly detection). This page shows real data captured at
      <strong>{generated_at}</strong> — it will not change again until the page is regenerated.
      The interactive version (live map, forecasts, alerts) runs locally.
    </p>
    <button onclick="document.getElementById('snapshot-modal').classList.add('hidden'); localStorage.setItem('sgSnapshotSeen','1')"
      class="w-full bg-[#DDD6FE] text-[#0F172A] font-semibold py-2.5 rounded-xl hover:bg-violet-200 transition-colors text-sm">
      Got it
    </button>
  </div>
</div>
<script>
  if (!localStorage.getItem('sgSnapshotSeen')) {{
    document.getElementById('snapshot-modal').classList.remove('hidden');
  }}
</script>

<header class="max-w-5xl mx-auto px-5 pt-10 pb-6">
  <a href="../index.html" class="text-sm text-violet-600 font-medium hover:underline">&larr; Back to portfolio</a>
  <h1 class="text-3xl font-extrabold mt-4 mb-2">🏙️ SG Transit Liveability Index</h1>
  <p class="text-[#0F172A]/60 max-w-2xl">Real-time transit connectivity + HDB value-for-money scoring across
  all 55 Singapore planning areas. Snapshot generated {generated_at}.</p>
</header>

<main class="max-w-5xl mx-auto px-5 pb-16 space-y-8">

  <section class="grid grid-cols-3 gap-4">
    <div class="bg-white rounded-2xl border border-[#DDD6FE]/40 p-5 text-center">
      <div class="text-3xl font-extrabold text-violet-500">{n_districts}</div>
      <div class="text-xs font-medium text-[#0F172A]/55 mt-1">Districts Monitored</div>
    </div>
    <div class="bg-white rounded-2xl border border-[#DDD6FE]/40 p-5 text-center">
      <div class="text-3xl font-extrabold text-sky-500">{avg_conn:.0f}</div>
      <div class="text-xs font-medium text-[#0F172A]/55 mt-1">Avg Connectivity Score</div>
    </div>
    <div class="bg-white rounded-2xl border border-[#DDD6FE]/40 p-5 text-center">
      <div class="text-3xl font-extrabold text-emerald-500">{avg_vfm:.0f}</div>
      <div class="text-xs font-medium text-[#0F172A]/55 mt-1">Avg Value-for-Money Score</div>
    </div>
  </section>

  <section class="bg-white rounded-2xl border border-[#DDD6FE]/40 p-6">
    <h2 class="font-bold text-lg mb-1">🏆 Connectivity Leaderboard · Top 10</h2>
    <p class="text-xs text-[#0F172A]/50 mb-4">Live transit score: bus frequency × 50% + taxi stability × 30% − friction × 20%.</p>
    {leaderboard_html}
  </section>

  <section class="bg-white rounded-2xl border border-[#DDD6FE]/40 p-6">
    <h2 class="font-bold text-lg mb-1">💰 Value-for-Money Ranking · Top 10</h2>
    <p class="text-xs text-[#0F172A]/50 mb-4">Blends transit connectivity with relative HDB resale-price affordability (50/50).</p>
    {vfm_html}
  </section>

  <section class="text-center py-6">
    <a href="https://github.com/hm-base/sg-transit-liveability" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 bg-[#DDD6FE] text-[#0F172A] font-semibold px-6 py-3 rounded-full hover:bg-violet-200 transition-all text-sm">
      View Full Source on GitHub
    </a>
  </section>

</main>

<footer class="bg-[#0F172A] text-white/50 py-6 text-center text-sm">
  Snapshot generated {generated_at} · SG Transit Liveability Index
</footer>

</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-repo", required=True,
                    help="Git URL or local path of the portfolio site repo to publish into")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        requests.get(f"{API_BASE}/health", timeout=5).raise_for_status()
    except Exception as e:
        sys.exit(f"Local API not reachable at {API_BASE} — run `python main.py` first.\n{e}")

    rank_data = fetch_json("/rank")
    vfm_data = fetch_json("/vfm", transport_weight=0.5)
    generated_at = datetime.now(SGT).strftime("%Y-%m-%d %H:%M SGT")

    html = build_page(rank_data, vfm_data, generated_at)

    with tempfile.TemporaryDirectory(prefix="sg-transit-static-") as tmp_str:
        clone = Path(tmp_str) / "site"
        run(["git", "clone", "--quiet", "--depth", "1", args.site_repo, str(clone)])

        page_path = clone / PAGE_SUBPATH
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(html, encoding="utf-8")

        run(["git", "-C", str(clone), "add", PAGE_SUBPATH])
        status = run(["git", "-C", str(clone), "status", "--porcelain"])
        if not status.stdout.strip():
            print("No changes since last snapshot — nothing to publish.")
            return

        run(["git", "-C", str(clone),
             "-c", "user.name=snapshot-publish",
             "-c", "user.email=snapshot-publish@users.noreply.github.com",
             "commit", "-m", f"Update SG Transit snapshot ({generated_at})"])

        if args.dry_run:
            print(f"--dry-run: page built at {page_path}, skipping push.")
            return

        run(["git", "-C", str(clone), "push", "origin", "HEAD"])
        print(f"Published snapshot ({generated_at}) to {args.site_repo}")


if __name__ == "__main__":
    main()
