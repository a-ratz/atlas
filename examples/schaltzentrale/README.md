# Demo-Vault „Schaltzentrale“

Ein kleines, komplett erfundenes Vault für einen Vortrag über das Gedächtnis von Agenten
(deutsch). Zwei Kundenprojekte in einer Gruppe mit gemeinsamen Regeln, ein paar Karten für
Personen und Organisationen, Threads, Entscheidungen und eine Lesson, die von einem Projekt
ins andere wandert.

| Was | Wo |
|---|---|
| Gruppenregeln, die jedes Projekt lädt | `vault/projects/kunden/_group.md` |
| Projekt A: Federkiel-Migration (Access-Ablösung) | `vault/projects/kunden/federkiel-migration/` |
| Projekt B: Ententeich-Portal (Import aus Access steht an) | `vault/projects/kunden/ententeich-portal/` |
| Die wandernde Lesson | `vault/projects/kunden/federkiel-migration/lessons/access-datum-als-lokale-zeit.md`, verlinkt in `_group.md` |
| Karten | `vault/cabinet/` |

## Starten (aus dem Repo-Wurzelordner)

```bash
uv run --no-project skills/atlas/app/engine/atlas.py --vault examples/schaltzentrale/vault serve --port 8766
```

Dann http://localhost:8766 öffnen.

## Der Moment für die Demo

```bash
uv run --no-project skills/atlas/app/engine/atlas.py --vault examples/schaltzentrale/vault boot ententeich-portal --agent copilot
```

Boot für Projekt B lädt die Gruppenregeln und unter „Lessons that apply“ die Lesson aus
Projekt A, markiert mit „(group)“. Fragt man einen Agenten danach, worauf beim Import der
Alttermine zu achten ist, kommt die Antwort aus der Federkiel-Migration.

Alle Namen, Firmen und Zahlen sind erfunden.
