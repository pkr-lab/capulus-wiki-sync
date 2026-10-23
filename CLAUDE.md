# CLAUDE.md — Arbeitsregeln für capulus-wiki-sync

Python-Programm (`wikisync`), das das Docs-Repo [pkr-lab-docs](https://github.com/pkr-lab/pkr-lab-docs) als Seitenbaum nach Wiki.js spiegelt. Läuft als CronJob im PROD-Cluster, das Helm-Chart liegt in [capulus-core](https://github.com/pkr-lab/capulus-core) (`argocd/apps/prod/wiki-docs-sync`). Sprache im Repo ist **Deutsch** (Docs, Commit-Beschreibungen, PR-Texte, Logmeldungen). Regeln wie in capulus-core.

---

## Harte Regeln

- **Keine Kommentare im Code.** Gilt für Python, Dockerfile und Workflows. Einzige Ausnahme: der Versions-Kommentar `# vX.Y.Z` hinter der Commit-SHA in `uses:`-Zeilen der Workflows (Renovate und Dependabot lesen ihn). Begründungen gehören ins Doc.
- **Doku liegt nicht in diesem Repo, sondern in [pkr-lab-docs](https://github.com/pkr-lab/pkr-lab-docs):** Betrieb und Aufbau in `capulus/capulus-core/wiki-sync.md`, Hintergründe unter `capulus/capulus-core/6-hintergruende/` (Zuordnung in `60000-uebersicht.md`). Jede Codeänderung bekommt dort einen PR. Konventionen stehen in der `CLAUDE.md` von pkr-lab-docs.
- **Nur Standardbibliothek.** Das Image kopiert nur `wikisync/` und installiert nichts (`python:3.14-slim`, Nutzer 1000). Keine neuen Abhängigkeiten ohne Rücksprache.
- **Niemals Tokens committen.** `WIKIJS_API_TOKEN` und `GITHUB_TOKEN` kommen nur aus der Umgebung (im Cluster als SealedSecret in capulus-core). gitleaks läuft in der CI (`.gitleaks.toml`).
- **Der Sync löscht Seiten in Wiki.js.** Änderungen an `sync.py` und `wikijs.py` besonders sorgfältig prüfen; die Sicherung `MIN_PAGES` und `DRY_RUN` nicht aufweichen.
- **Nie direkt auf `main` arbeiten.** Änderungen gehen nur per PR hinein (der Branch-Schutz auf GitHub ist hier nicht aktiv, die Regel gilt trotzdem). Steht das Arbeitsverzeichnis auf `main`, vor der ersten Änderung einen neuen Branch anlegen (`git switch -c <typ>/<kurzbeschreibung>`, z. B. `feat/backup-retention`, `fix/ca-pin`) und nur dort arbeiten. Den Branch legt Claude an, Commit, Push und PR macht der Nutzer.

---

## Wo was liegt

| Pfad | Inhalt |
|---|---|
| `wikisync/__main__.py` | Einstieg; Exit-Code 2 bei fehlender Konfiguration |
| `wikisync/config.py` | `Config.from_env`, alle Einstellungen per Umgebungsvariable |
| `wikisync/source.py` | lädt den Tarball des Docs-Repos über die GitHub-API und liest den Baum |
| `wikisync/render.py` | Seiten bauen: Pfade, Links und Bilder umschreiben, Übersichtsseiten erzeugen |
| `wikisync/wikijs.py` | GraphQL-Client für Wiki.js |
| `wikisync/sync.py` | Abgleich: anlegen, ändern, löschen |
| `tests/` | `unittest`, Hilfen in `tests/helpers.py` (`make_config`) |

Wichtige Variablen: `WIKIJS_API_URL`, `WIKIJS_API_TOKEN` (Pflicht), `WIKIJS_PATH_PREFIX` (Standard `docs`), `GITHUB_OWNER`/`GITHUB_REPO`/`GITHUB_BRANCH`/`GITHUB_TOKEN`, `EXCLUDE`, `WIKIJS_LEGACY_PREFIXES`, `MIN_PAGES` (Standard 20), `DRY_RUN`.

---

## Prüfen vor dem Commit

Die CI (`.github/workflows/ci.yml`) hat drei Pflicht-Jobs: `unittest`, `docker build` (der Aufruf ohne Konfiguration muss mit Exit-Code 2 enden), gitleaks.

```bash
python3 -m unittest discover -s . -t .
docker build -t capulus-wiki-sync:ci . && docker run --rm capulus-wiki-sync:ci; echo $?
```

Gegen ein echtes Wiki.js nur mit `DRY_RUN=true` und nur durch den Nutzer; die Sandbox erreicht weder das Wiki noch das LAN.

---

## Code-Stil

- Typannotationen überall, `dataclass(frozen=True)` für Werte, Fehler als eigene Exceptions (`ConfigError`, `CollisionError`, `WikiError`).
- Logmeldungen mit Präfix (`[CREATE]`, `[FATAL]` usw.), Fehler nach stderr.
- Zu jeder Verhaltensänderung in `render.py` oder `sync.py` gehört ein Test in `tests/`.

---

## Commits und PRs

- **Claude committet und pusht nicht.** Commits, Pushes und PRs macht ausschließlich der Nutzer. Änderungen nur im Arbeitsverzeichnis vorbereiten, am Ende kurz zusammenfassen und einen passenden Commit-Text vorschlagen. Ausnahme nur, wenn der Nutzer es in der jeweiligen Anfrage ausdrücklich verlangt.
- Conventional Commits mit Scope = Modul, Beschreibung auf Deutsch: `feat(render): …`, `fix(sync): …`, `docs(…): …`. Typen: feat fix docs chore refactor test ci build perf style revert.
  `feat`/`fix` lösen über semantic-release ein Release aus (zentraler Workflow in `pkr-lab/.github`, CHANGELOG.md und Tag `vX.Y.Z`); capulus-core zieht das neue Image per Renovate nach. Der Commitlint-Check läuft auf PRs; lokal prüft `git config core.hooksPath .githooks` das Format.
- Ein PR = eine Änderung inkl. zugehöriger Doku. Renovate-PRs nicht manuell nachbauen.
