#!/usr/bin/env python3
"""
Annual report script for the PyLadies Germany Fund.

Fetches all closed GitHub issues for a given year and reports:
- How many issues were closed
- How much budget was used (EUR amounts from approval requests)

Usage:
    python scripts/annual_report.py [--year YEAR] [--token TOKEN] [--repo REPO]

Environment variables:
    GITHUB_TOKEN  GitHub personal access token (optional for public repos)
    GITHUB_REPOSITORY  Repository in "owner/repo" format (default: PyLadiesGermany/PySV_PyLadies_fund)
"""

import argparse
import os
import re
import sys
import urllib.request
import urllib.error
import json
from datetime import datetime, timezone


REPO_DEFAULT = "PyLadiesGermany/PySV_PyLadies_fund"
GITHUB_API = "https://api.github.com"


def fetch_issues(repo: str, token: str | None, year: int) -> list[dict]:
    """Fetch all closed issues for the given year from GitHub API."""
    issues = []
    page = 1

    since = f"{year}-01-01T00:00:00Z"

    while True:
        url = (
            f"{GITHUB_API}/repos/{repo}/issues"
            f"?state=closed&per_page=100&page={page}"
            f"&since={since}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                page_issues = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            print(f"Error fetching issues: {e}", file=sys.stderr)
            sys.exit(1)

        if not page_issues:
            break

        for issue in page_issues:
            # Skip pull requests
            if "pull_request" in issue:
                continue

            closed_at = issue.get("closed_at")
            if not closed_at:
                continue

            closed_year = datetime.fromisoformat(
                closed_at.replace("Z", "+00:00")
            ).year
            if closed_year == year:
                issues.append(issue)

        page += 1

    return issues


def extract_eur_amount(title: str) -> float | None:
    """
    Extract EUR amount from issue title.

    Handles formats like:
        [357 EUR]
        [3,184.72 EUR]
        [105,46 EUR]   (German decimal comma)
        [208.40 EUR]
        [+386 EUR Donation]
        [5000 EUR Donation]
        772,17 EUR
    """
    # Match patterns like:
    #   [357 EUR]         — optional brackets, plain integer
    #   [+386 EUR ...]    — optional leading plus (donations)
    #   [105,46 EUR]      — German decimal comma
    #   [3,184.72 EUR]    — thousands separator + decimal point
    #   772,17 EUR        — no brackets
    pattern = r"\[?\s*\+?\s*([\d,\.]+)\s*EUR"
    match = re.search(pattern, title, re.IGNORECASE)
    if not match:
        return None

    raw = match.group(1)

    # Normalise German decimal comma notation:
    # "3,184.72"  → already valid float
    # "105,46"    → 105.46  (comma is decimal separator)
    # "294,31"    → 294.31
    if "," in raw and "." in raw:
        # Both present: comma is thousands separator (e.g. 3,184.72)
        raw = raw.replace(",", "")
    elif "," in raw:
        # Only comma: treat as decimal separator (German style)
        raw = raw.replace(",", ".")

    try:
        return float(raw)
    except ValueError:
        return None


def is_budget_request(issue: dict) -> bool:
    """Return True if the issue is a fund approval request (not a donation or meta issue)."""
    labels = [
        (lbl["name"] if isinstance(lbl, dict) else lbl)
        for lbl in issue.get("labels", [])
    ]
    return "approval_request" in labels


def generate_report(issues: list[dict], year: int) -> str:
    """Generate a human-readable report."""
    budget_issues = [i for i in issues if is_budget_request(i)]

    total_budget = 0.0
    parsed_issues = []
    unparsed_issues = []

    for issue in budget_issues:
        amount = extract_eur_amount(issue["title"])
        if amount is not None:
            total_budget += amount
            parsed_issues.append((issue["number"], issue["title"], amount))
        else:
            unparsed_issues.append((issue["number"], issue["title"]))

    lines = [
        f"# PyLadies Germany Fund — Annual Report {year}",
        "",
        f"## Summary",
        f"",
        f"- **Total issues closed in {year}:** {len(issues)}",
        f"- **Approval requests closed in {year}:** {len(budget_issues)}",
        f"- **Total budget used:** {total_budget:,.2f} EUR",
        "",
        "## Approval Requests",
        "",
    ]

    if parsed_issues:
        lines.append("| Issue | Title | Amount (EUR) |")
        lines.append("| ----- | ----- | ------------ |")
        for number, title, amount in sorted(parsed_issues, key=lambda x: x[0]):
            lines.append(f"| #{number} | {title} | {amount:,.2f} |")
    else:
        lines.append("_No approval requests found._")

    if unparsed_issues:
        lines += [
            "",
            "## Issues with unrecognised amount format",
            "",
        ]
        for number, title in unparsed_issues:
            lines.append(f"- #{number}: {title}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an annual budget report from GitHub Issues."
    )
    parser.add_argument(
        "--year",
        type=int,
        default=datetime.now(timezone.utc).year - 1,
        help="Year to report on (default: last calendar year)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub personal access token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", REPO_DEFAULT),
        help=f"Repository in owner/repo format (default: {REPO_DEFAULT})",
    )
    args = parser.parse_args()

    print(
        f"Fetching closed issues for {args.repo} in {args.year}…",
        file=sys.stderr,
    )
    issues = fetch_issues(args.repo, args.token, args.year)
    print(f"Found {len(issues)} closed issues.", file=sys.stderr)

    report = generate_report(issues, args.year)
    print(report)


if __name__ == "__main__":
    main()
