# PLAN

## Cel

Ten plik opisuje **jak etapami wdrazac caly zakres z `FUTURE.md`** bez rozwalenia architektury, UX i szybkiego workflow `lcView`.

To jest plan operacyjny:

- w jakiej kolejnosci robic rzeczy,
- co grupowac razem,
- czego nie mieszac w jednym PR,
- kiedy dany etap uznac za domkniety.

## Status

### Zrobione

- **Etap 0 - Fundament**  
  Powstaly `FUTURE.md` i `PLAN.md`, jest rozpisana kolejnosc wdrozen, podzial na paczki i kryteria domkniecia.

- **Etap 1 - Display i UX**  
  Zrealizowane:
  - log-scale DFT,
  - Nyquist indicator,
  - DFT range / grid advice,
  - keyboard shortcuts dla glownego workflow,
  - rozszerzony eksport wynikow do `CSV`, `TSV`, `LaTeX` i `TXT`,
  - ulepszony model `frequency_error`.

- **Etap 2 - Statystyka DFT**  
  Zrealizowane:
  - spectral window jako opcjonalny overlay,
  - local noise estimation dla calego periodogramu,
  - adaptive S/N dla klasyfikacji kandydatow,
  - przelaczanie widoku amplitude / S/N spectrum,
  - odswiezanie selekcji i markerow bez gubienia wybranego piku.

### Do zrobienia teraz

- **Etap 3 - Lomb-Scargle**
  - dodanie backendu `lombscargle`,
  - integracja z obecnym wyborem backendu,
  - spiecie z obecnym workflow wynikow i peak selection.

## Zasady realizacji

1. Robic **male, zamykalne etapy** zamiast jednej dlugiej galezi.
2. Kazdy etap powinien miec osobny PR albo serie malych PR w ramach jednego epiku.
3. Nie laczyc w jednym PR:
   - nowego algorytmu,
   - duzego I/O,
   - przebudowy UI,
   - zmian statystyki,
   jesli nie sa bezposrednio zalezne.
4. Najpierw zmiany o **niskim ryzyku i duzej wartosci**.
5. Nowe funkcje domyslnie dodawac za:
   - checkbox,
   - combobox,
   - jawna akcja uzytkownika,
   zeby nie psuc obecnego workflow.
6. Zachowac szybki model pracy:
   - `fwpeaks` pozostaje domyslnym szybkim backendem,
   - `Fit model` nie moze nagle zaczac odpalac wolnych obliczen,
   - ciezsze rzeczy tylko jako osobne akcje albo worker.
7. Przy zmianach UI pilnowac calego lancucha:
   - tabela kandydatow / accepted
   - `selected_frequency`
   - marker na DFT
   - phase controls
   - powiazane wykresy

## Definition of done dla kazdego etapu

Kazdy etap powinien byc domkniety tak:

1. `core` gotowy i dziala samodzielnie,
2. ustawienia zapisane w `session`,
3. UI spiete z logika,
4. testy dla warstwy numerycznej i / lub GUI,
5. update dokumentacji, jesli zmienia sie workflow lub output.

## Kolejnosc glownych etapow

| Etap | Nazwa | Zakres | Priorytet |
|---|---|---|---|
| 0 | Fundament | backlog, issue breakdown, acceptance criteria | bardzo wysoki |
| 1 | Display i UX | szybkie usprawnienia bez zmiany core workflow | bardzo wysoki |
| 2 | Statystyka DFT | lepsza interpretacja pikow i aliasow | bardzo wysoki |
| 3 | Lomb-Scargle | nowy backend periodogramu | wysoki |
| 4 | FAP | formalna istotnosc pikow | wysoki |
| 5 | FITS i metadane czasu | nowoczesny input danych | wysoki |
| 6 | Workflow phase / harmonics | szybsza analiza modulacji i harmonicznych | sredni-wysoki |
| 7 | BLS | transit / eclipsing workflow | sredni |
| 8 | Barycentric corrections | precyzja czasu | sredni |
| 9 | PDM / AOV | analiza przebiegow niesinusoidalnych | sredni |
| 10 | Echelle | zaawansowana wizualizacja asterosejsmologiczna | sredni |
| 11 | Period-spacing | zaawansowana analiza patternow | sredni |
| 12 | O-C | analiza zmian okresu | sredni |
| 13 | Multi-file comparison | porownania datasetow / sezonow / pasm | niski-sredni |
| 14 | MAST integration | bezposrednie pobieranie danych | niski |

## Etap 0 - Fundament

**Status:** done

### Cel

Przygotowac projekt tak, zeby dalsze wdrozenia byly przewidywalne.

### Zakres

- rozbic `FUTURE.md` na epiki i mniejsze issue,
- ustalic zaleznosci miedzy etapami,
- ustalic acceptance criteria dla najblizszych 3-4 etapow,
- ustalic, co jest:
  - default behavior,
  - optional behavior,
  - advanced workflow.

### Wynik etapu

- gotowy backlog wykonawczy,
- uzgodniona kolejnosc PR,
- jasne granice odpowiedzialnosci kolejnych etapow.

## Etap 1 - Display i UX

**Status:** done

### Zakres

- log-scale DFT,
- Nyquist indicator + ostrzezenia o zakresie,
- keyboard shortcuts,
- rozszerzenie eksportu wynikow,
- lepszy model `frequency_error`.

### Dlaczego najpierw

Bo daje szybka wartosc, male ryzyko i nie przebudowuje architektury.

### Pliki najbardziej dotkniete

- `src/lcview/ui/main_window.py`
- `src/lcview/ui/plots.py`
- `src/lcview/ui/results_panel.py`
- `src/lcview/core/results.py`
- `src/lcview/core/session.py`

### Exit criteria

- log-scale dziala bez psucia obecnych wykresow,
- Nyquist line jest czytelna i konfigurowalna,
- eksport daje sensowny output do dalszej pracy,
- frequency uncertainties sa bardziej realistyczne,
- skroty nie wchodza w konflikt z edycja tabel i pol formularza.

## Etap 2 - Statystyka DFT

**Status:** done

### Zakres

- spectral window,
- local noise estimation,
- adaptive S/N.

### Dlaczego osobno

To jest jeden wspolny obszar: interpretacja widma DFT.

### Pliki najbardziej dotkniete

- `src/lcview/core/periodogram.py`
- `src/lcview/ui/main_window.py`
- `src/lcview/ui/plots.py`
- `src/lcview/core/session.py`

### Exit criteria

- mozna wyswietlic spectral window bez rozwalania zwyklego DFT workflow,
- peak interpretation jest oparta o lokalne tlo,
- GUI jasno pokazuje, czy user patrzy na amplitude, S/N i jakie tlo jest uzyte.

## Etap 3 - Lomb-Scargle

**Status:** next

### Zakres

- dodanie backendu `lombscargle`,
- integracja z obecnym wyborem backendu,
- spiecie z obecnym workflow wynikow i peak selection.

### Dlaczego osobno

To nowy backend, ale jeszcze bez mieszania z FAP i bez ruszania FITS.

### Pliki najbardziej dotkniete

- `src/lcview/core/periodogram.py`
- `src/lcview/ui/main_window.py`
- `src/lcview/core/session.py`

### Exit criteria

- backend dziala rownolegle do `fwpeaks`,
- user moze jawnie wybrac LS,
- output jest sensownie mapowany na obecne UI.

## Etap 4 - FAP

### Zakres

- False Alarm Probability dla Lomb-Scargle,
- opcjonalnie pozniej bootstrap / resampling dla DFT.

### Dlaczego po LS

Bo `Astropy` daje gotowe i sensowne mechanizmy FAP dla LS, wiec to najprostszy punkt startowy.

### Exit criteria

- user widzi poziom istotnosci albo wartosc FAP,
- wiadomo, jaka metoda FAP zostala uzyta,
- GUI nie sugeruje falszywej precyzji tam, gdzie wynik jest przyblizeniem.

## Etap 5 - FITS i metadane czasu

### Zakres

- FITS import,
- obsluga typowych light curve formatow TESS/Kepler/K2,
- przechowanie metadanych czasu potrzebnych do dalszych etapow.

### Dlaczego tutaj

Dopiero po ustabilizowaniu wykresow i statystyki warto otworzyc szeroko wejscie na nowe dane.

### Pliki najbardziej dotkniete

- `src/lcview/core/lightcurve.py`
- `src/lcview/core/session.py`
- `src/lcview/ui/main_window.py`

### Exit criteria

- mozna otworzyc standardowy FITS bez recznych obejsc,
- user rozumie, jakie kolumny / serie sa wczytywane,
- nowe dane nie psuja obecnego loadera tekstowego.

## Etap 6 - Workflow phase / harmonics

### Zakres

- phase plot colored by epoch,
- harmonic suggestion po dodaniu nowej czestotliwosci.

### Dlaczego osobno

To poprawa codziennego workflow analitycznego, ale juz na bazie stabilniejszego I/O.

### Pliki najbardziej dotkniete

- `src/lcview/core/phase.py`
- `src/lcview/ui/main_window.py`
- `src/lcview/ui/plots.py`
- `src/lcview/core/combinations.py`

### Exit criteria

- kolorowanie po epoce nie psuje wydajnosci i czytelnosci,
- harmonic suggestions pomagaja, ale niczego nie dodaja automatycznie bez zgody usera.

## Etap 7 - BLS

### Zakres

- Box Least Squares jako osobny tryb / backend,
- podstawowe ustawienia duration / period grid,
- sensowna prezentacja wyniku.

### Dlaczego osobno

To inny przypadek naukowy niz klasyczny sinusoidalny prewhitening.

### Exit criteria

- BLS nie miesza sie z klasycznym DFT UX,
- user wie, kiedy ma sens BLS, a kiedy DFT / LS.

## Etap 8 - Barycentric corrections

### Zakres

- time standard conversion,
- barycentric correction,
- przechowanie potrzebnych metadanych obserwatora i obiektu.

### Dlaczego po FITS

Najpierw trzeba miec porzadne wsparcie czasu i danych wejsciowych.

### Exit criteria

- korekty sa jawne i odwracalne,
- user widzi, z jakiego standardu do jakiego przechodzi.

## Etap 9 - PDM / AOV

### Zakres

- dodanie PDM,
- opcjonalnie AOV jako kolejny backend / tryb.

### Dlaczego tu

To osobna rodzina metod, przydatna po ustabilizowaniu LS i BLS.

### Exit criteria

- algorytm dziala dla obiektow niesinusoidalnych,
- UI nie myli interpretacji DFT / LS / PDM.

## Etap 10 - Echelle

### Zakres

- echelle diagram,
- podstawowa kontrola separation / modulo,
- czytelne zaznaczenie accepted frequencies.

### Exit criteria

- widok jest wystarczajaco dobry do realnej pracy, a nie tylko demo.

## Etap 11 - Period-spacing

### Zakres

- search / helper dla period-spacing patterns,
- powiazanie z zaakceptowanymi czestotliwosciami / okresami.

### Exit criteria

- wynik jest interpretowalny i powtarzalny,
- user rozumie zalozenia algorytmu.

## Etap 12 - O-C

### Zakres

- liczenie observed minus calculated,
- wykres O-C,
- podstawowy workflow ephemeris.

### Exit criteria

- da sie zrobic realny O-C workflow bez recznego eksportu do innego narzedzia.

## Etap 13 - Multi-file comparison

### Zakres

- overlay DFT / phase z kilku plikow albo sezonow,
- porownania pre/post-correction.

### Dlaczego pozno

Bo to duza ingerencja w model aplikacji i ryzyko chaosu w stanie UI.

### Exit criteria

- user nie gubi sie, ktory dataset jest aktualnie aktywny,
- porownania sa czytelne i nie psuja single-file workflow.

## Etap 14 - MAST integration

### Zakres

- pobieranie po identyfikatorze,
- podstawowy search / download flow,
- cache albo lokalna obsluga pobranych plikow.

### Dlaczego na koncu

Bo to zaleznosci sieciowe, nowe UX, potencjalnie nowe biblioteki i najwieksza powierzchnia zmian poza sama analiza.

### Exit criteria

- pobieranie jest stabilne,
- user rozumie, co zostalo pobrane i skad,
- integracja nie komplikuje prostego lokalnego workflow.

## Paczki wdrozen, ktore warto robic jako osobne PR

Rekomendowana praktyczna paczka po paczce:

1. `log-scale DFT + Nyquist + export formats + frequency errors + shortcuts`
2. `spectral window + local noise + adaptive S/N`
3. `Lomb-Scargle`
4. `FAP`
5. `FITS import + time metadata`
6. `epoch-colored phase + harmonic suggestions`
7. `BLS`
8. `barycentric corrections`
9. `PDM/AOV`
10. `echelle`
11. `period-spacing`
12. `O-C`
13. `multi-file comparison`
14. `MAST integration`

## Czego nie mieszac w jednym PR

Przyklady:

- nie laczyc `Lomb-Scargle` z `FITS import`,
- nie laczyc `BLS` z `PDM/AOV`,
- nie laczyc `frequency_error` z duza przebudowa wynikow GUI,
- nie laczyc `multi-file comparison` z `MAST integration`,
- nie laczyc `barycentric corrections` z pierwszym wdrozeniem FITS.

## Minimalna strategia na start

Jesli celem jest wejsc w temat bez chaosu, to najlepszy start jest taki:

1. Etap 1
2. Etap 2
3. Etap 3
4. Etap 4
5. Etap 5

To daje:

- lepsze wykresy,
- lepsza interpretacje pikow,
- nowy backend,
- formalna istotnosc,
- nowoczesny input danych.

To juz bardzo mocno podnosi wartosc `lcView`, zanim zaczna sie najtrudniejsze moduly naukowe.
