"""Обчислення метрик DORA (Лаб 10, Етап 2).

Джерело — ``docs/ci-cd/evidence/ci-runs.json``.

* ``docs/ci-cd/metrics-raw.md`` — таблиця всіх запусків (Етап 1);
* підсумкові числа виводяться в консоль для ``dora-summary.md``.

Розгортання рахуються по комітах на ``main``, а не по запусках: коміт
запускає два workflow (CI і деплой документації), і підрахунок запусків
подвоїв би частоту. Коміт зелений, якщо всі його завершені запуски
успішні; червоний, якщо впав хоча б один. Скасовані запуски
(``cancelled``) не вважаються збоєм зміни.

Запуск: ``python3 scripts/compute_dora.py``
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

RUNS = Path("docs/ci-cd/evidence/ci-runs.json")
RAW_TABLE = Path("docs/ci-cd/metrics-raw.md")
KYIV = ZoneInfo("Europe/Kyiv")
REPO_URL = "https://github.com/ukma-fin-ssdm-2026/noproblem"
SHORT_WORKFLOW = {
    "CI": "CI",
    "Generate and Deploy API Docs": "API Docs",
}


def ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def local(moment: datetime | None) -> str:
    return moment.astimezone(KYIV).strftime("%d.%m %H:%M") if moment else ""


def minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60


def failure_note(run: dict) -> str:
    if run["conclusion"] == "cancelled":
        return "скасовано; не рахується як збій зміни"
    steps = sorted({s for job in run["jobs"] for s in job["failedSteps"]})
    log = " ".join(run.get("failedLogTail", []))
    reason = ""
    if "Fail if committed spec is stale" in steps:
        reason = "закомічена OpenAPI-специфікація не збіглася зі згенерованою"
        return f"впав крок: {', '.join(steps)}; {reason}"
    for marker, text in (
        ("504", "HTTP 504 під час завантаження Python"),
        ("timed out", "тайм-аут"),
        ("Error:", ""),
    ):
        if marker in log:
            reason = text
            break
    note = "впав крок: " + ", ".join(steps) if steps else "збій"
    return f"{note}; {reason}" if reason else note


def prepare(runs: list[dict]) -> list[dict]:
    rows = []
    for run in runs:
        jobs = [j for j in run["jobs"] if j["startedAt"]]
        created = ts(run["createdAt"])
        started = min(ts(j["startedAt"]) for j in jobs)
        finished = max(ts(j["completedAt"]) for j in jobs)
        pr = run.get("pullRequest") or {}
        rows.append(
            {
                "sha": run["headSha"],
                "workflow": SHORT_WORKFLOW.get(
                    run["workflowName"], run["workflowName"]
                ),
                "conclusion": run["conclusion"],
                "created": created,
                "finished": finished,
                "queue": minutes(started - created),
                "exec": minutes(finished - started),
                "pr": pr.get("number"),
                "first_commit": ts(pr.get("firstCommitAuthoredAt")),
                "note": (
                    "" if run["conclusion"] == "success" else failure_note(run)
                ),
            }
        )
    rows.sort(key=lambda row: row["created"])
    return rows


def write_raw_table(rows: list[dict]) -> None:
    first, last = rows[0]["created"], rows[-1]["created"]
    lines = [
        "# Сирі метрики запусків CI/CD",
        "",
        f"Усі {len(rows)} запусків на `main` з історії GitHub Actions за "
        f"{local(first)[:5]}–{local(last)[:5]}.2026: workflow `CI` і "
        "`Generate and Deploy API Docs` (у таблиці — «API Docs»). Час "
        "наведено в Europe/Kyiv. Черга — від `createdAt` запуску до "
        "найранішого `startedAt` його завдань; виконання — від "
        "найранішого `startedAt` до найпізнішого `completedAt`. Хвилини "
        "округлено до цілих. Дані зібрано скриптом "
        "`scripts/collect_ci_metrics.py`, таблицю згенеровано "
        "`scripts/compute_dora.py`.",
        "",
        "| № | Коміт | Workflow | PR | Перший коміт PR | Запуск "
        "завершено | Черга, хв | Виконання, хв | Статус | Примітка |",
        "|---:|---|---|---:|---|---|---:|---:|:---:|---|",
    ]
    status = {"success": "✅", "failure": "❌", "cancelled": "⚪"}
    for index, row in enumerate(rows, start=1):
        pr = (
            f"[#{row['pr']}]({REPO_URL}/pull/{row['pr']})"
            if row["pr"]
            else "—"
        )
        lines.append(
            f"| {index} | `{row['sha'][:7]}` | {row['workflow']} | {pr} | "
            f"{local(row['first_commit'])} | {local(row['finished'])} | "
            f"{round(row['queue'])} | {round(row['exec'])} | "
            f"{status.get(row['conclusion'], row['conclusion'])} | "
            f"{row['note']} |"
        )
    lines += [
        "",
        "✅ успішний · ❌ невдалий · ⚪ скасований.",
        "",
        "## File was created by Claude, verified and modified by "
        "Kozynska Anastasia ##",
        "",
    ]
    RAW_TABLE.write_text("\n".join(lines), encoding="utf-8")


def commits(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["sha"], []).append(row)
    result = []
    for sha, runs in grouped.items():
        done = [r for r in runs if r["conclusion"] != "cancelled"]
        if not done:
            continue
        failed = [r for r in done if r["conclusion"] == "failure"]
        last = max(done, key=lambda r: r["finished"])
        result.append(
            {
                "sha": sha,
                "pr": runs[0]["pr"],
                "first_commit": runs[0]["first_commit"],
                "created": min(r["created"] for r in runs),
                "finished": last["finished"],
                "queue": last["queue"],
                "exec": last["exec"],
                "green": not failed,
                "failed_at": (
                    min(r["finished"] for r in failed) if failed else None
                ),
            }
        )
    result.sort(key=lambda c: c["created"])
    return result


def describe(values: list[float], unit: str = "год") -> str:
    if not values:
        return "—"
    mean, median = statistics.mean(values), statistics.median(values)
    return f"середнє {mean:.1f} {unit}, медіана {median:.1f} {unit}"


def main() -> None:
    runs = json.loads(RUNS.read_text(encoding="utf-8"))
    rows = prepare(runs)
    write_raw_table(rows)
    items = commits(rows)

    period_seconds = (rows[-1]["created"] - rows[0]["created"]).total_seconds()
    period_weeks = period_seconds / 86400 / 7
    green = [c for c in items if c["green"]]
    red = [c for c in items if not c["green"]]
    gaps = [
        (b["finished"] - a["finished"]).total_seconds() / 3600
        for a, b in zip(green, green[1:])
    ]
    lead = [
        (c["finished"] - c["first_commit"]).total_seconds() / 3600
        for c in green
        if c["first_commit"]
    ]
    recoveries = []
    for index, item in enumerate(items):
        if item["green"] or (index and not items[index - 1]["green"]):
            continue
        nxt = next((c for c in items[index + 1 :] if c["green"]), None)
        if nxt:
            recoveries.append(
                (nxt["finished"] - item["failed_at"]).total_seconds() / 60
            )
    queue = [c["queue"] for c in green if c["first_commit"]]
    execute = [c["exec"] for c in green if c["first_commit"]]
    run_success = sum(r["conclusion"] == "success" for r in rows)
    run_done = sum(r["conclusion"] in ("success", "failure") for r in rows)

    print(
        f"Період: {local(rows[0]['created'])} – {local(rows[-1]['created'])}"
        f" ({period_weeks:.2f} тиж.)"
    )
    print(
        f"Запусків: {len(rows)}; комітів: {len(items)}; "
        f"зелених: {len(green)}; червоних: {len(red)}"
    )
    print(
        f"Частота: {len(green) / period_weeks:.1f} на тиждень; "
        f"медіана інтервалу між розгортаннями {statistics.median(gaps):.1f}"
        " год"
    )
    print(f"Час виконання змін ({len(lead)} комітів з PR): {describe(lead)}")
    print(
        f"  черга: {describe(queue, 'хв')}; виконання: "
        f"{describe(execute, 'хв')}"
    )
    mean_lead_min = statistics.mean(lead) * 60
    print(
        f"  частка черги {statistics.mean(queue) / mean_lead_min:.2%}, "
        f"виконання {statistics.mean(execute) / mean_lead_min:.2%} "
        "середнього часу виконання змін"
    )
    print(
        f"Частота збоїв: {len(red)}/{len(items)} = "
        f"{len(red) / len(items):.1%}"
    )
    print(
        f"Відновлення (хв): {[round(r) for r in recoveries]}; "
        f"{describe(recoveries, 'хв')}"
    )
    print(
        f"Частка успішних запусків: {run_success}/{run_done} = "
        f"{run_success / run_done:.1%} (скасованих: "
        f"{sum(r['conclusion'] == 'cancelled' for r in rows)})"
    )
    print(
        f"Тривалість запуску: медіана "
        f"{statistics.median(r['exec'] for r in rows):.1f} хв"
    )
    for item in red:
        print(
            f"  червоний: {item['sha'][:7]} PR #{item['pr']} "
            f"{local(item['failed_at'])}"
        )


if __name__ == "__main__":
    main()


# File was created by Claude, verified and modified by Kozynska Anastasia
