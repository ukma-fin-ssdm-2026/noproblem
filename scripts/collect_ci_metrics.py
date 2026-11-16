"""Збір сирих даних запусків CI для Лабораторної 10 (Етап 1).

Скрипт через GitHub CLI (``gh``) бере останні запуски на ``main`` і
зберігає в ``docs/ci-cd/evidence/ci-runs.json`` для кожного:

* workflow, статус, час створення запуску;
* час початку першого й завершення останнього завдання (з них
  рахуються черга й виконання);
* PR, з якого злито коміт, і час першого коміту цього PR;
* для червоного запуску — назви впалих кроків і кінець логу.

Запити виконуються паралельно, а дані про коміт і PR кешуються, тож
90 запусків збираються приблизно за хвилину.

Запуск із кореня репозиторію (потрібен ``gh auth login``)::

    python3 scripts/collect_ci_metrics.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "ukma-fin-ssdm-2026/noproblem"
OUTPUT = Path("docs/ci-cd/evidence/ci-runs.json")
RUN_LIMIT = 90
WORKERS = 8
LOG_TAIL_LINES = 40

_pr_cache: dict[str, dict | None] = {}
_pr_lock = threading.Lock()


def gh_json(*args: str) -> object:
    result = subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    )
    return json.loads(result.stdout)


def gh_text(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True
    ).stdout


def run_jobs(run_id: int) -> list[dict]:
    data = gh_json(
        "api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"
    )
    return [
        {
            "name": job["name"],
            "conclusion": job["conclusion"],
            "startedAt": job["started_at"],
            "completedAt": job["completed_at"],
            "failedSteps": [
                step["name"]
                for step in job.get("steps", [])
                if step.get("conclusion") == "failure"
            ],
        }
        for job in data["jobs"]
    ]


def pull_request_for(sha: str) -> dict | None:
    with _pr_lock:
        if sha in _pr_cache:
            return _pr_cache[sha]
    pulls = gh_json("api", f"repos/{REPO}/commits/{sha}/pulls")
    merged = [pr for pr in pulls if pr.get("merged_at")] or pulls
    info = None
    if merged:
        pr = merged[0]
        commits = gh_json(
            "api",
            f"repos/{REPO}/pulls/{pr['number']}/commits?per_page=1",
        )
        info = {
            "number": pr["number"],
            "title": pr["title"],
            "createdAt": pr["created_at"],
            "mergedAt": pr["merged_at"],
            "firstCommitAuthoredAt": (
                commits[0]["commit"]["author"]["date"] if commits else None
            ),
        }
    with _pr_lock:
        _pr_cache[sha] = info
    return info


def enrich(run: dict) -> dict:
    run_id = run["databaseId"]
    try:
        run["jobs"] = run_jobs(run_id)
        run["pullRequest"] = pull_request_for(run["headSha"])
        if run["conclusion"] in ("failure", "timed_out", "cancelled"):
            log = gh_text(
                "run", "view", str(run_id), "--repo", REPO, "--log-failed"
            )
            run["failedLogTail"] = log.splitlines()[-LOG_TAIL_LINES:]
    except subprocess.CalledProcessError as error:
        run["collectError"] = (error.stderr or str(error)).strip()
    print(f"  {run['workflowName']} {run_id}", file=sys.stderr)
    return run


def main() -> int:
    try:
        subprocess.run(["gh", "auth", "status"], check=True,
                       capture_output=True, text=True)
    except FileNotFoundError:
        print("Не знайдено gh: встановіть GitHub CLI.", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError:
        print("gh не автентифіковано: виконайте gh auth login.",
              file=sys.stderr)
        return 1
    runs = gh_json(
        "run",
        "list",
        "--repo",
        REPO,
        "--branch",
        "main",
        "--limit",
        str(RUN_LIMIT),
        "--json",
        "databaseId,headSha,workflowName,conclusion,attempt,createdAt,"
        "updatedAt,event,status,displayTitle,url",
    )
    print(f"Знайдено запусків: {len(runs)}", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        runs = list(pool.map(enrich, runs))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(runs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    errors = sum(1 for run in runs if "collectError" in run)
    print(
        f"Збережено {len(runs)} запусків у {OUTPUT}; помилок: {errors}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


# File was created by Claude, verified and modified by Kozynska Anastasia
