# Demo-Skript, 5 Minuten

Jede Frage hier ist gegen die laufende App geprüft, mit dem Ergebnis, das darunter steht.
Die vier Fragen liegen auch als Klick-Buttons im leeren Q&A-Fenster, du musst nichts tippen.
Alle Fragen sind auf Deutsch oder Englisch, passend zum Publikum. Die Gesetze darunter sind
französisch, italienisch und englisch, und genau dieser Bruch ist der Vorführeffekt.

## Vorher, zwei Minuten vor dem Start

```
cd ~/Documents/"ReMeP Hackathon 2026"/ReMeP_Hackathon_26
uv run python app.py
```

1. http://localhost:5050 öffnen.
2. **Eine Aufwärmfrage stellen** und das Ergebnis wegklicken. Der erste Aufruf baut den
   Knowledge Graph und parst die XML-Dokumente, das dauert ein bis zwei Sekunden länger.
3. Terminal in einem zweiten Fenster sichtbar lassen. Wenn dort `[llm_agent] … unavailable`
   auftaucht, hat OpenRouter nicht geantwortet und die Antwort kommt aus dem
   deterministischen Fallback, der die Jurisdiktion nicht erkennt.
4. Browser-Zoom auf 110 bis 125 Prozent, das Dokumentenfenster rechts hat kleine Schrift.

**Wenn das Netz stirbt:** Compliance Check und Knowledge Graph laufen komplett ohne LLM.
Nur der Q&A-Modus braucht OpenRouter. Das ist kein Notnagel, sondern genau dein Argument:
das Urteil hängt nicht am Sprachmodell.

## Ablauf

### 1. Sprachgrenze zwischen Frage und Gesetz, 45 Sekunden

> `Wie lange gilt das Urheberrecht in Frankreich?`

Deutsche Frage, französisches Gesetz, deutsche Antwort, zitiert **Art. L123-1 CPI**.
Rechts steht der Artikel im französischen Original aus dem AKN-Dokument.

Das ist der Punkt, den ein deutsch- und englischsprachiges Publikum direkt nachvollziehen
kann: die Frage und das Gesetz sind in verschiedenen Sprachen, und die Zahl in der Antwort
kommt nicht aus dem Modell, sondern aus dem Graphen. Das Modell übersetzt und formuliert,
es rechnet nicht.

### 2. Der Grenzfall, 60 Sekunden

> `How long does copyright last in New Zealand?`

Antwort: 50 Jahre, **s. 22 Copyright Act 1994**. Dann in den Tab **Compliance Check** und
Neuseeland wählen: compliant, mit Abstand null zum Berne-Minimum von 50 Jahren.

Das ist der stärkste Moment im Demo. Alle anderen acht Jurisdiktionen liegen bei 70,
Neuseeland liegt exakt auf der Schwelle. Ein Modell, das Zahlen schätzt, würde hier
plausibel raten. Der Vergleich ist eine SPARQL-Abfrage plus ein Zahlenvergleich, kein LLM.

### 3. Knowledge Graph, 90 Sekunden

Tab **Knowledge Graph**, Jurisdiktion **European Union** wählen.

Der Graph zeigt zwei Gesetzesknoten unter der EU: die Schutzdauer steht in
Richtlinie 2006/116, die Verwertungsrechte und die Privatkopie-Ausnahme in
InfoSoc 2001/29. Genau die Sorte Verteilung, die man von Hand übersieht.

Dann **auf einen Knoten klicken**, zum Beispiel auf `Copyright duration`. Links unten
erscheinen alle Triples dieses Knotens, darüber die SPARQL-Abfrage, die den Subgraphen
geliefert hat. Das ist der Explicability-Punkt aus deiner Future-Work-Folie, nur live:
welche Triples, welche Provision, welcher Vergleich.

Zum Vergleich noch **Germany** wählen: ein Gesetz, alle drei Regeltypen darin, und die
gestrichelte `compliesWith`-Kante zur Berne-Konvention.

### 4. Zeitachse, 60 Sekunden

> `Wie lange dauert der Urheberrechtsschutz in Italien?`

Antwort: 70 Jahre, Art. 25 LDA. Jetzt der interessante Teil, und du solltest ihn selbst
ansprechen, bevor es jemand im Publikum tut:

Der Artikeltext rechts sagt **cinquantesimo**, also 50. Darunter steht die
Normattiva-Notiz `AGGIORNAMENTO (14)`: die L. 52/1996 hat die Fristen der Artikel 25, 26,
27, 27-bis, 31, 32 und 32-bis auf 70 Jahre angehoben. Normattiva schreibt den Artikel
nicht um, sondern hängt die Änderung als Notiz an. Wer die Zahl per Regex aus dem
Gesetzestext zieht, bekommt 50 und liegt falsch. Der Graph kodiert die konsolidierte
Zahl 70, und die Notiz im Dokument belegt sie.

Dann rechts im Feld **Version** die Liste aufklappen: 68 Versionen mit ihren Daten, von
1941-07-16 bis 2025-12-18. Nimm eine frühe, etwa **1946-09-13**. Derselbe Artikel, ohne die
Änderungsnotiz, weil es die Änderung damals noch nicht gab.

Alternativ tippst du ins Feld **or date** ein beliebiges Datum, zum Beispiel 1975-06-15,
dann löst das System auf die Version auf, die an diesem Tag in Kraft war, hier die vom
1975-03-10. Das Badge oben zeigt danach das Datum der geladenen Version, nicht dein
Eingabedatum. Datum vor 1941-07-16 sagt explizit, dass es keine Fassung gibt.

## Wenn Zeit übrig ist

- `Which economic rights does Canada recognize?` → s. 3 Copyright Act, fünf Rechte als
  Liste. Kanada und Neuseeland liegen in ihren nationalen XML-Formaten vor, ohne eIds, und
  wurden für dieses Projekt nach AKN konvertiert (`scripts/04_convert_national_xml_to_akn.py`).
- `Wie lange dauert der Urheberrechtsschutz in Deutschland?` → § 64 UrhG, kürzester
  Gesetzestext im Korpus, ein Satz. Gut, wenn eine Frage sofort sitzen soll.
- `Does the United States have a private-use exception?` → § 107, fair use.
- Im Point-in-Time-Modus `art_71-sexies` auf 1950 setzen: die Vorschrift gab es noch nicht,
  das System sagt das explizit statt einen Fehler zu zeigen.
- **Official Source** im Metadatenbalken öffnet die Seite des Gesetzgebers, für Deutschland
  gesetze-im-internet.de, für die EU die EUR-Lex-Seite der jeweiligen Richtlinie. Daneben
  steht grau die FRBR-Work-URI, das ist der Identifier, kein Link.

## Was du an den Folien noch anpassen solltest

- **Folie 10 und 11** nennen Gemini 2.0 Flash. Das Modell ist bei OpenRouter abgeschaltet,
  aktuell läuft Gemini 2.5 Flash mit zwei kostenlosen Gemma-Modellen als Fallback.
- **Folie 8** listet als EU-Quelle nur die Richtlinie 2006/116. Dazu kommt jetzt
  InfoSoc 2001/29, konsolidierte Fassung vom 2019-06-06.
- **Folie 8** sagt, alle neun Jurisdiktionen seien als AKN kodiert. Das stimmt jetzt,
  vorher galt es für Kanada und Neuseeland nicht.
- **Folie 13** zeigt zwei von Hand gebaute Graphen. Die kannst du durch einen Screenshot
  aus dem neuen Knowledge-Graph-Tab ersetzen, dann ist es der echte Graph.

## Fragen, die kommen könnten

**Warum ist die Antwort nicht halluziniert?**
Die Zahl und der Artikelverweis kommen aus dem Graphen, das Modell formuliert nur. Der
Compliance-Vergleich läuft ohne Modell. Im Knowledge-Graph-Tab sieht man die Triples.

**Warum steht bei manchen Dokumenten kein Authenticity-Badge?**
Nur die Schweiz und das Vereinigte Königreich liefern offizielle AKN-Exporte. Alles andere
sind Konversionen, und die markieren wir als nicht authentisch, statt Authentizität zu
behaupten. Die Original-URL steht in den FRBR-Metadaten.

**Skaliert das auf 190 WIPO-Mitgliedsstaaten?**
Der Graph und die Abfragen ja. Der Aufwand liegt in der AKN-Konversion pro Land, ein
Format pro Gesetzgeber. Kanada und Neuseeland haben je einen eigenen Adapter gebraucht.
