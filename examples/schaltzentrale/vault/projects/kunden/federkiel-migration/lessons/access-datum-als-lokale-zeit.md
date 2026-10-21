---
status: validated
applies_to: kunden
evidence: 312 von 41.000 Lieferdaten einen Tag zu früh nach dem ersten Import; nach der Korrektur 0 Abweichungen
created_by: copilot
updated_by: copilot
---

# Wenn Datumswerte aus Access kommen, Kalenderdaten ohne Zeitzone übernehmen und nie über UTC umrechnen

Access speichert Datum/Uhrzeit als Kommazahl (Tage seit dem 30.12.1899) ohne Zeitzone.
Unser erster Import hat die Werte als lokale Zeit gelesen, in UTC gespeichert und das
Datum später aus dem UTC-Wert abgeleitet. Ein Liefertermin „30.03.2026 00:00“ wurde so zu
„29.03.2026 22:00 UTC“ und stand in der Oberfläche am 29.03. Getroffen hat es alle Werte
um Mitternacht.

**Regel:** Reine Kalenderdaten (Liefertermin, Ablesetermin) als Datum ohne Uhrzeit und
Zone übernehmen. Echte Zeitpunkte bewusst mit Europe/Berlin versehen und das Datum nie aus
dem UTC-Wert ableiten. Im Golden Master mindestens einen Wert um Mitternacht und einen am
Tag der Zeitumstellung prüfen.

## Log
- 2026-10-14 (copilot): beim Abgleich der Altbestellungen gefunden.
- 2026-10-16 (copilot): validiert: Import wiederholt, 0 Abweichungen auf 41.000 Datensätzen.
