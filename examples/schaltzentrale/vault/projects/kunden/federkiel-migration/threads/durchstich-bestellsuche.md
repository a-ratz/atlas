---
status: open
next: Golden Master für die Suche nach Lieferdatum am Original aufzeichnen
created_by: copilot
updated_by: copilot
---

# Durchstich Bestellsuche

Die Bestellsuche geht als erstes Paket einmal komplett durch: Referenz, Umsetzen,
Vergleichen, Abnehmen.

## Log
- 2026-10-14 (copilot): Import der 41.000 Altbestellungen fertig. Beim Abgleich mit dem
  Original lagen 312 Lieferdaten einen Tag zu früh. Ursache und Regel:
  [[access-datum-als-lokale-zeit]].
- 2026-10-16 (copilot): Import mit lokaler Zeit wiederholt, alle 41.000 Datensätze gleich
  mit dem Original (Vergleichsskript, 0 Abweichungen).
- 2026-10-20 (copilot): Suche nach Kundennummer und Status grün gegen 18 Golden Master.
  Suche nach Lieferdatum noch ohne Referenzfälle.
