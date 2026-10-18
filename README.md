# capulus-wiki-sync

Spiegelt das Docs-Repo [pkr-lab-docs](https://github.com/pkr-lab/pkr-lab-docs) in ein Wiki.js: Ordnerstruktur bleibt als Seitenbaum erhalten, relative Links und Bilder werden umgeschrieben, Übersichtsseiten entstehen automatisch, geänderte Seiten werden aktualisiert und entfernte gelöscht. Läuft als CronJob im PROD-Cluster, ausgerollt über [capulus-core](https://github.com/pkr-lab/capulus-core) (`argocd/apps/prod/wiki-docs-sync`).

## Quickstart

```bash
python3 -m unittest discover -s . -t .

WIKIJS_API_URL=http://localhost:3000 WIKIJS_API_TOKEN=... DRY_RUN=true python3 -m wikisync
```

Mit `DRY_RUN=true` listet das Programm nur, was es anlegen, ändern oder löschen würde.

## Dokumentation

[Betrieb und Aufbau](https://github.com/pkr-lab/pkr-lab-docs/blob/main/capulus-core/wiki-sync.md) · [Releases](https://github.com/pkr-lab/pkr-lab-docs/blob/main/capulus-core/releases.md)

## Lizenz

MIT, siehe [LICENSE](LICENSE).
