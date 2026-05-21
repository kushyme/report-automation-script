#!/usr/bin/env python3
"""Generate a weekly training report draft from git history.

The script keeps the factual collection local and deterministic. Junie can be
used optionally for the final wording if the Junie CLI is installed and
authenticated.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JUNIE_EMPTY_OUTPUT_MARKER = "<!-- report_automation_waiting_for_junie -->"


class JunieCliNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class Commit:
    hash: str
    date: str
    author: str
    subject: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class Workday:
    date: dt.date

    @property
    def label(self) -> str:
        weekday_names = {
            0: "Montag",
            1: "Dienstag",
            2: "Mittwoch",
            3: "Donnerstag",
            4: "Freitag",
            5: "Samstag",
            6: "Sonntag",
        }
        return f"{weekday_names[self.date.weekday()]}, {self.date:%d.%m.%Y}"


def start_of_week(today: dt.date) -> dt.date:
    return today - dt.timedelta(days=today.weekday())


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def collect_workdays(since: str, until: str, include_weekends: bool) -> list[Workday]:
    start = parse_date(since)
    end = parse_date(until)
    if end < start:
        raise ValueError("--until darf nicht vor --since liegen.")

    days: list[Workday] = []
    current = start
    while current <= end:
        if include_weekends or current.weekday() < 5:
            days.append(Workday(current))
        current += dt.timedelta(days=1)
    return days


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def get_default_author() -> str | None:
    try:
        return run_git(["config", "user.name"]) or None
    except subprocess.CalledProcessError:
        return None


def collect_commits(since: str, until: str, author: str | None) -> list[Commit]:
    pretty_format = "--COMMIT--%n%h%n%ad%n%an%n%s"
    git_args = [
        "log",
        f"--since={since}",
        f"--until={until}",
        "--reverse",
        "--date=short",
        f"--pretty=format:{pretty_format}",
        "--name-only",
    ]
    if author:
        git_args.insert(1, f"--author={author}")

    output = run_git(git_args)
    if not output:
        return []

    commits: list[Commit] = []
    for block in output.split("--COMMIT--"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 4:
            continue

        commit_hash, date, commit_author, subject, *files = lines
        commits.append(
            Commit(
                hash=commit_hash,
                date=date,
                author=commit_author,
                subject=subject,
                files=tuple(files),
            )
        )
    return commits


def categorize_file(path: str) -> str:
    if "/test/" in path or path.endswith(".test.ts") or "__snapshots__" in path:
        return "Tests und Qualitätssicherung"
    if path.startswith("src/backend/") or path.startswith("lambda/"):
        return "Backend und AWS-Infrastruktur"
    if path.startswith("src/frontend/"):
        return "Frontend"
    if path.startswith("docs/") or path == "README.md":
        return "Dokumentation"
    if path.startswith("tools/") or path in {"package.json", "pnpm-lock.yaml", "cdk.json"}:
        return "Build, Deployment und Tooling"
    return "Sonstiges"


def summarize_categories(commits: list[Commit]) -> dict[str, set[str]]:
    categories: dict[str, set[str]] = {}
    for commit in commits:
        for file_path in commit.files:
            categories.setdefault(categorize_file(file_path), set()).add(file_path)
    return categories


def group_commits_by_date(commits: list[Commit]) -> dict[str, list[Commit]]:
    grouped: dict[str, list[Commit]] = {}
    for commit in commits:
        grouped.setdefault(commit.date, []).append(commit)
    return grouped


def build_day_context(workdays: list[Workday], commits: list[Commit]) -> str:
    commits_by_date = group_commits_by_date(commits)
    day_blocks: list[str] = []

    for workday in workdays:
        date_key = workday.date.isoformat()
        day_commits = commits_by_date.get(date_key, [])
        if not day_commits:
            day_blocks.append(
                f"{workday.label}\n"
                "- Keine passenden eigenen Git-Commits im ausgewählten Zeitraum gefunden."
            )
            continue

        commit_lines = "\n".join(
            f"- {commit.hash}: {commit.subject}\n"
            f"  Dateien: {', '.join(commit.files[:12]) if commit.files else 'keine Dateiliste'}"
            for commit in day_commits
        )
        day_blocks.append(f"{workday.label}\n{commit_lines}")

    return "\n\n".join(day_blocks)


def build_prompt(
        commits: list[Commit],
        since: str,
        until: str,
        workdays: list[Workday],
        daily_time: str,
        daily_text: str,
) -> str:
    categories = summarize_categories(commits)
    commit_lines = "\n".join(
        f"- {commit.date} {commit.hash}: {commit.subject} ({commit.author})\n"
        f"  Dateien: {', '.join(commit.files[:12]) if commit.files else 'keine Dateiliste'}"
        for commit in commits
    )
    category_lines = "\n".join(
        f"- {category}: {', '.join(sorted(files)[:20])}"
        for category, files in sorted(categories.items())
    )
    day_context = build_day_context(workdays, commits)

    return f"""Erstelle einen professionellen Berichtsheft-Eintrag auf Deutsch für die Ausbildung.

Zeitraum: {since} bis {until}

Gewünschtes Ausgabeformat:
- Gib ausschließlich den fertigen Berichtsheft-Text aus, ohne Einleitung wie "Hier ist..." und ohne abschließenden Kommentar.
- Schreibe für jeden aufgeführten Arbeitstag einen eigenen Abschnitt.
- Nutze je Tag eine Markdown-Überschrift im Format: ## Montag, 18.05.2026
- Schreibe pro Tag einen zusammenhängenden Absatz aus vollen Sätzen.
- Verwende keine Stichpunkte, keine Bulletpoints, keine nummerierten Listen und keine Labels wie "Projektarbeit:" oder "09:15 Uhr:".
- Jeder Tagesabschnitt soll mit dem Daily in der Ich-Form beginnen, zum Beispiel: Ich habe um {daily_time} Uhr am {daily_text} teilgenommen.
- Danach beschreibst du die fachlichen Tätigkeiten des Tages anhand der Git-Logs.
- Die Tonalität soll professionell, sachlich, natürlich und ausbildungsgeeignet sein.
- Schreibe mit normalen deutschen Umlauten, also ä, ö und ü statt ae, oe oder ue.

Stilvorbild:
- Formuliere ähnlich wie ein fertiger Berichtsheft-Eintrag: "Im weiteren Verlauf des Tages habe ich mich mit ..." oder "Nach der Teilnahme am Daily ... habe ich ...".
- Schreibe konkret genug, dass die Tätigkeit nachvollziehbar ist, aber nicht werblich oder übertrieben.
- Nutze technische Begriffe aus den Commits und Dateinamen, z. B. cdk-nag, ARM_64, API-Stack, Monitoring-Stack, Lambda-Handler, Pre-Deployment-Skript oder Architektur-Skizze, wenn sie im Tageskontext vorkommen.
- Wiederhole nicht mechanisch jeden Commit-Betreff, sondern formuliere daraus saubere Tätigkeiten für das Berichtsheft.
- Erkläre bei passenden Git-Daten kurz den Zweck der Tätigkeit, z. B. Best Practices, Sicherheitsanforderungen, Typsicherheit, Code-Struktur, Performance oder Kosteneffizienz.
- Wenn Commit-Betreff und Dateinamen darauf hindeuten, darfst du konkrete Formulierungen ableiten, zum Beispiel: cdk-nag als Arbeit an Infrastruktur-Best-Practices, Architektur-Skizzen als Projektdokumentation, Pre-Deployment-Skripte als automatisierte Prüfung vor Deployments, Änderungen an Lambda-Handlern als Refactoring oder Strukturverbesserung und ARM_64 als Performance- und Kostenoptimierung.

Inhaltliche Regeln:
- Schreibe konsequent in der Ich-Form.
- Verwende aktive Formulierungen mit "ich", z. B. "ich habe erstellt", "ich habe angepasst", "ich habe integriert", "ich habe aktualisiert" oder "ich habe mich beschäftigt".
- Vermeide neutrale oder passive Formulierungen wie "es wurde angepasst", "wurde entwickelt", "wurden aktualisiert", "der Schwerpunkt lag" oder "zur Sicherstellung wurden".
- Jeder Tagesabschnitt muss mehrere Ich-Formulierungen enthalten, sobald es fachliche Tätigkeiten an diesem Tag gibt.
- Verwende nur Informationen aus den Git-Logs.
- Die einzige feste Zusatzinformation, die immer verwendet werden darf, ist das Daily um {daily_time} Uhr.
- Erfinde keine weiteren Meetings, keine nicht belegten Lerninhalte und keine nicht belegten Ergebnisse.
- Formuliere ausbildungsgeeignet, konkret und nicht übertrieben.
- Wenn an einem Tag keine Git-Commits vorhanden sind, schreibe nach dem Daily vorsichtig, dass keine final ins Versionskontrollsystem übertragenen Arbeitsergebnisse vorliegen. Formuliere dann allgemein, dass der Fokus auf Nachbereitung, Dokumentation oder Planung lag, ohne konkrete technische Details zu erfinden.

Thematische Dateibereiche:
{category_lines or "- Keine Dateibereiche gefunden"}

Tageskontext:
{day_context or "- Keine Arbeitstage im Zeitraum gefunden"}

Git-Logs:
{commit_lines or "- Keine Commits im Zeitraum gefunden"}
"""


def run_junie(prompt: str, output: Path, model: str | None) -> None:
    junie_command = find_junie_command()
    if not junie_command:
        raise JunieCliNotFound(
            "Es wurde keine ausführbare Junie CLI gefunden. "
            "Gefundene kaputte Installationen wurden übersprungen."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(JUNIE_EMPTY_OUTPUT_MARKER + "\n", encoding="utf-8")
    task = build_junie_file_task(prompt, output)

    command = [*junie_command, "--output-format", "text"]
    if model:
        command.extend(["--model", model])
    command.append(task)

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    content = output.read_text(encoding="utf-8").strip()
    if not content or content == JUNIE_EMPTY_OUTPUT_MARKER:
        raise RuntimeError(
            "Junie wurde ausgeführt, hat aber die Berichtsheft-Datei nicht geschrieben."
        )


def build_junie_file_task(prompt: str, output: Path) -> str:
    output_path = output.resolve()
    return f"""{prompt}

Wichtig für diese CLI-Ausführung:
- Schreibe den finalen Berichtsheft-Text direkt in diese Markdown-Datei: {output_path}
- Der Inhalt dieser Datei muss ausschließlich der fertige Berichtsheft-Text sein.
- Schreibe keine TASK RESULT Summary, keine Changes-Liste, keine Verification-Liste und keine ANSI-Farbcodes in die Datei.
- Verändere keine anderen Dateien.
- Wenn die Datei bereits existiert, überschreibe ihren Inhalt vollständig.
"""


def find_junie_command() -> list[str] | None:
    candidates: list[Path] = []

    if os.environ.get("JUNIE_BIN"):
        candidates.append(Path(os.environ["JUNIE_BIN"]).expanduser())

    candidates.extend(find_all_on_path("junie"))

    local_junie = Path.home() / ".local" / "bin" / "junie"
    candidates.append(local_junie)

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        if is_working_junie(candidate):
            return [str(candidate)]

    return None


def find_all_on_path(binary_name: str) -> list[Path]:
    matches: list[Path] = []
    for path_entry in os.environ.get("PATH", "").split(os.pathsep):
        if not path_entry:
            continue
        candidate = Path(path_entry) / binary_name
        if candidate.exists() and os.access(candidate, os.X_OK):
            matches.append(candidate)
    return matches


def is_working_junie(candidate: Path) -> bool:
    if not candidate.exists() or not os.access(candidate, os.X_OK):
        return False

    try:
        subprocess.run(
            [str(candidate), "--version"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False

    return True


def format_junie_error(error: BaseException) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        details = (error.stderr or error.stdout or str(error)).strip()
        if details:
            return details
    return str(error)


def default_output_path(since: str, until: str, prompt_only: bool) -> Path:
    suffix = "prompt" if prompt_only else "bericht"
    return PROJECT_ROOT / "docs" / f"berichtsheft-{since}-bis-{until}-{suffix}.md"


def prompt_fallback_output_path(since: str, until: str, output: Path | None) -> Path:
    if output:
        return output.with_name(f"{output.stem}-prompt{output.suffix or '.md'}")
    return default_output_path(since, until, prompt_only=True)


def write_report(content: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content + "\n", encoding="utf-8")
    print(f"Fertig: {output}")


def parse_args() -> argparse.Namespace:
    today = dt.date.today()
    default_since = start_of_week(today).isoformat()
    default_until = today.isoformat()
    default_author = get_default_author()

    parser = argparse.ArgumentParser(
        description="Erstellt einen Berichtsheft-Entwurf aus Git-Logs.",
    )
    parser.add_argument("--since", default=default_since, help="Startdatum, z. B. 2026-05-18")
    parser.add_argument("--until", default=default_until, help="Enddatum, z. B. 2026-05-21")
    parser.add_argument(
        "--author",
        default=default_author,
        help="Git-Autor-Filter. Standard ist git config user.name.",
    )
    parser.add_argument(
        "--all-authors",
        action="store_true",
        help="Alle Autoren einbeziehen und den Autor-Filter deaktivieren.",
    )
    parser.add_argument(
        "--include-weekends",
        action="store_true",
        help="Auch Samstag und Sonntag im Tagesbericht ausgeben.",
    )
    parser.add_argument(
        "--daily-time",
        default="09:15",
        help="Uhrzeit für das tägliche Daily.",
    )
    parser.add_argument(
        "--daily-text",
        default="Daily zum Azubi-Austausch",
        help="Beschreibung des täglichen Daily-Termins.",
    )
    parser.add_argument(
        "--use-junie",
        action="store_true",
        help="Junie CLI für die finale Formulierung verwenden. Das ist inzwischen der Standard.",
    )
    parser.add_argument(
        "--junie-model",
        help="Optionales Junie-Modell, z. B. sonnet.",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Nur den Prompt ausgeben, der an Junie gegeben werden kann.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Zieldatei für den Entwurf. Standard ist "
            "docs/berichtsheft-<since>-bis-<until>-bericht.md."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    author = None if args.all_authors else args.author

    try:
        workdays = collect_workdays(args.since, args.until, args.include_weekends)
        commits = collect_commits(args.since, args.until, author)
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f"Berichtsheft-Daten konnten nicht gelesen werden: {error}", file=sys.stderr)
        return 1

    prompt = build_prompt(
        commits,
        args.since,
        args.until,
        workdays,
        args.daily_time,
        args.daily_text,
    )
    output = args.output or default_output_path(args.since, args.until, args.prompt_only)
    if args.prompt_only:
        write_report(prompt, output)
        return 0

    try:
        run_junie(prompt, output, args.junie_model)
    except JunieCliNotFound:
        prompt_output = prompt_fallback_output_path(args.since, args.until, args.output)
        write_report(prompt, prompt_output)
        print(
            "Hinweis: Junie CLI wurde nicht gefunden. "
            "Ich habe stattdessen den Prompt gespeichert, den du in Junie in IntelliJ einfügen kannst."
        )
        print("Installiere Junie CLI, wenn der finale Bericht automatisch erstellt werden soll.")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        prompt_output = prompt_fallback_output_path(args.since, args.until, args.output)
        write_report(prompt, prompt_output)
        error_message = format_junie_error(error)
        print(
            "Hinweis: Junie konnte nicht ausgeführt werden. "
            "Ich habe stattdessen den Prompt gespeichert, den du in Junie in IntelliJ einfügen kannst."
        )
        print(f"Junie-Fehler: {error_message}", file=sys.stderr)
        return 0

    print(f"Fertig: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
