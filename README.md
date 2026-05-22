# Report Automation Script

Ein kleines Python-Script, mit dem ich meine Berichtsheft-Einträge aus Git-Commits vorbereite.

## Warum ich das gemacht habe

Ich habe das Script geschrieben, weil ich mein Berichtsheft nicht jedes Mal komplett von Hand aus dem Kopf schreiben wollte. Viele Informationen stehen bei mir sowieso schon in der Git-Historie: was ich geändert habe, an welchen Dateien ich gearbeitet habe und in welchem Zeitraum das passiert ist.

Das Script soll mir diese wiederkehrende Arbeit abnehmen. Es sammelt die passenden Git-Commits, baut daraus einen Prompt und lässt daraus mit der Junie CLI einen ersten Berichtsheft-Entwurf schreiben.

Der fertige Text ist nicht dafür gedacht, blind abgegeben zu werden. Ich nutze ihn als Grundlage und prüfe danach selbst, ob alles stimmt und ob etwas ergänzt werden muss.

## Was das Script macht

- liest Git-Commits in einem bestimmten Zeitraum aus
- filtert standardmäßig nach dem eigenen Git-Autor
- erstellt Abschnitte für die Arbeitstage im Zeitraum
- gruppiert Commits nach Datum
- erkennt grob, ob Dateien eher zu Frontend, Backend, Tests, Dokumentation oder Tooling gehören
- erstellt daraus einen deutschen Prompt für einen Berichtsheft-Eintrag
- nutzt die Junie CLI, um daraus einen Markdown-Entwurf zu schreiben
- speichert den Prompt als Fallback, falls Junie nicht verfügbar ist

## Voraussetzungen

Die Voraussetzungen stehen auch in [Requirements.txt](Requirements.txt).

Benötigt wird:

- Python 3.10 oder neuer
- Git
- Junie CLI

Die Junie CLI muss installiert und angemeldet sein, wenn der fertige Bericht automatisch erzeugt werden soll. Ohne Junie speichert das Script nur den Prompt, den man anschließend manuell verwenden kann.

## Nutzung

Für die aktuelle Woche bis heute:

```bash
python3 report-automation.py
```

Für einen bestimmten Zeitraum:

```bash
python3 report-automation.py --since 2026-05-18 --until 2026-05-22
```

Nur den Prompt erstellen:

```bash
python3 report-automation.py --since 2026-05-18 --until 2026-05-22 --prompt-only
```

Alle Autoren einbeziehen:

```bash
python3 report-automation.py --since 2026-05-18 --until 2026-05-22 --all-authors
```

Eigene Ausgabedatei setzen:

```bash
python3 report-automation.py --output docs/mein-berichtsheft.md
```

Eine bestimmte Junie-Binary verwenden:

```bash
JUNIE_BIN=/pfad/zur/junie python3 report-automation.py
```

## Ausgabe

Standardmäßig schreibt das Script Dateien in den Ordner `docs/`.

Bericht:

```text
docs/berichtsheft-<since>-bis-<until>-bericht.md
```

Prompt:

```text
docs/berichtsheft-<since>-bis-<until>-prompt.md
```

## Hinweise

Das Ergebnis hängt davon ab, wie gut die Git-Commits geschrieben sind. Wenn an einem Tag keine passenden Commits vorhanden sind, kann das Script auch keine konkreten Tätigkeiten daraus ableiten.

Interne Projektdetails, echte Berichtshefte oder personenbezogene Daten sollten nicht ungeprüft in ein öffentliches Repository übernommen werden.
