# FUTURE

## Cel

Ten plik zbiera propozycje ulepszen dla `lcView` na podstawie:

- przegladu obecnego kodu i GUI,
- publikacji i materialow o analizie light curves, period finding i prewhitening,
- porownania z dojrzalymi narzedziami: `Period04`, `VStar`, `Lightkurve`, `Astropy`.

To nie jest sztywny plan releasow. To jest uporzadkowana roadmapa: co warto dodac, co daje najwieksza wartosc i w jakiej kolejnosci najlepiej to robic.

## Stan obecny lcView

`lcView` ma juz mocne podstawy do pracy naukowej i nie potrzebuje przepisywania od zera. Aktualnie ma m.in.:

- natywny backend DFT `fwpeaks`,
- Python backend DFT jako tryb jawny,
- weighted least-squares fit,
- iteracyjny prewhitening,
- harmonic/combinations detection,
- phase folding i sin/cos overlays,
- TDFD do analizy modulacji w czasie,
- sigma clipping z podgladem,
- Akima detrending,
- session persistence,
- alias markers (daily/yearly),
- eksport wynikow do CSV oraz kopiowanie TSV,
- GUI do pracy interaktywnej na danych.

## Najwieksze luki wzgledem narzedzi referencyjnych

Najbardziej widoczne braki wzgledem `Period04`, `VStar`, `Lightkurve` i `Astropy`:

1. Brak alternatywnych metod period finding poza DFT.
2. Brak mocniejszej warstwy statystycznej: `FAP`, local noise, adaptive S/N.
3. Brak kilku bardzo uzytecznych wizualizacji: log-scale DFT, spectral window, epoch-colored phase plot, echelle.
4. Brak nowoczesnego I/O dla photometrii kosmicznej: FITS, time-standard conversion.
5. Brak kilku prostych ulepszen UX, ktore mocno przyspiesza codzienna prace.

## Priorytetowa roadmapa

### Etap 1 - Quick wins

Najlepszy stosunek wartosci do kosztu:

| Funkcja | Po co | Wysilek |
|---|---|---|
| Log-scale DFT amplitude axis | Lepiej widac slabe mody przy duzej dynamice amplitud | niski |
| Nyquist indicator + range advice | Chroni przed blednym zakresem czestotliwosci i aliasami | niski |
| Spectral window overlay | Bardzo pomaga odroznic piki prawdziwe od aliasow | niski-sredni |
| Keyboard shortcuts | Przyspiesza prewhitening przy duzej liczbie modow | niski |
| Lepszy wzor na frequency uncertainty | Daje bardziej realistyczne niepewnosci | niski |
| Rozszerzenie eksportu wynikow | CSV juz jest; warto dodac LaTeX i bardziej publikacyjny output | niski |

### Etap 2 - Statystyka i wiarygodnosc wynikow

| Funkcja | Po co | Wysilek |
|---|---|---|
| Local noise estimation | Lepsza ocena pikow niz jeden globalny poziom szumu | niski-sredni |
| Adaptive S/N | Urealnia prog istotnosci w roznych czesciach widma | niski-sredni |
| False Alarm Probability (FAP) | Formalna ocena istotnosci pikow | sredni |
| Lomb-Scargle backend | Lepszy backend dla danych nierownomiernie probkowanych i pod FAP | sredni |

### Etap 3 - I/O i workflow nowoczesnych danych

| Funkcja | Po co | Wysilek |
|---|---|---|
| FITS import | Otwiera wygodny workflow dla TESS/Kepler/K2 | sredni |
| Phase plot colored by epoch | Szybciej ujawnia modulacje amplitudy/fazy | niski-sredni |
| Harmonic suggestion | Mniej klikania przy obiektach z silnymi harmonicznymi | niski-sredni |
| BLS mode | Przydatny dla transitow i eclipsing binaries | sredni |

### Etap 4 - Advanced science modules

| Funkcja | Po co | Wysilek |
|---|---|---|
| Echelle diagram | Klasyczne narzedzie asterosejsmologiczne | sredni-wysoki |
| Period-spacing search | Duza wartosc naukowa dla g-mode/p-mode patternow | wysoki |
| O-C diagrams | Analiza zmian okresu i companion effects | wysoki |
| Barycentric time correction | Poprawia precyzje czasowa | sredni |
| PDM/AOV | Dobre dla niesinusoidalnych przebiegow | sredni |
| Multi-file comparison | Porownanie sezonow, pasm i przetworzonych wersji danych | wysoki |

## Top 5 do zrobienia najpierw

Jesli wybierac tylko piec rzeczy na start:

1. **Log-scale DFT + Nyquist + spectral window**
2. **Local noise + adaptive S/N**
3. **Lomb-Scargle + FAP**
4. **Lepszy frequency uncertainty model**
5. **FITS import**

Powod:

- sa bardzo uzyteczne praktycznie od razu,
- dobrze pasuja do obecnej architektury,
- nie wymagaja przepisywania calego silnika,
- zamykaja najwieksze luki wzgledem standardowych workflow naukowych.

## Pelny backlog pomyslow

### 1. Algorytmy i period finding

1. **Lomb-Scargle backend**  
   Alternatywny backend periodogramu dla danych nierownomiernie probkowanych. Dobrze integruje sie z `Astropy` i ulatwia dodanie FAP.

2. **BLS (Box Least Squares)**  
   Tryb do wykrywania transitow i eclipsing binaries, gdzie sinusoidalny model nie jest najlepszym przyblizeniem.

3. **PDM / AOV**  
   Szczegolnie przydatne dla obiektow z niesinusoidalnym ksztaltem krzywej zmian.

### 2. Statystyka i niepewnosci

4. **False Alarm Probability (FAP)**  
   Formalny odpowiednik pytania: czy ten pik moze byc przypadkowym szumem?

5. **Montgomery & O'Donoghue style frequency uncertainties**  
   Zastapienie prostego przyblizenia opartego glownie o baseline wzorem uwzgledniajacym amplitude, baseline, liczbe obserwacji i residual noise.

6. **Local noise estimation**  
   Szum liczony lokalnie po widmie, a nie jednym globalnym parametrem.

7. **Adaptive S/N threshold**  
   Prog istotnosci zalezy od lokalnego tla widma, a nie od jednego stalego poziomu.

### 3. I/O i interoperacyjnosc

8. **FITS import**  
   Wczytywanie standardowych light curve FITS bez potrzeby recznego eksportu do tekstu.

9. **Rozszerzony eksport wynikow**  
   CSV juz jest. Warto dodac:
   - LaTeX table,
   - lepszy plain text export,
   - ewentualnie gotowy "paper table" z frequency / period / amplitude / phase / uncertainties / SNR.

10. **MAST / astroquery integration**  
    Pobieranie danych po TIC/KIC/EPIC bezposrednio z GUI. Bardzo przydatne, ale kosztowniejsze i wymaga rozwazenia zaleznosci.

11. **Barycentric time correction / time standard conversion**  
    Konwersje typu JD/HJD/BJD(TDB) z uzyciem `astropy.time`.

### 4. Wizualizacja

12. **Spectral window plot / overlay**  
    Pokazuje alias pattern wynikajacy z samego probkowania.

13. **Log-scale DFT / SNR spectrum view**  
    Ulatwia ogladanie slabych modow i szerokiej dynamiki amplitud.

14. **Phase plot colored by epoch**  
    Punkty pokolorowane czasem obserwacji, dzieki czemu od razu widac modulacje i dryf.

15. **Echelle diagram**  
    Dla asterosejsmologii: szybka identyfikacja powtarzalnych struktur modowych.

16. **Nyquist indicator**  
    Linia i ostrzezenia dla efektywnego Nyquista oraz zbyt grubego kroku w siatce czestotliwosci.

### 5. Nauka / analiza zaawansowana

17. **Period-spacing pattern detection**  
    Automatyczne szukanie wzorcow spacing w zestawie zaakceptowanych czestotliwosci/okresow.

18. **O-C diagram**  
    Analiza zmian okresu i potencjalnych companion signatures.

### 6. UX i workflow

19. **Keyboard shortcuts**  
    Np. szybkie accept/remove/recompute/zoom bez ciaglego klikania.

20. **Automated harmonic suggestion**  
    Po zaakceptowaniu nowej czestotliwosci proponowanie 2f, 3f, 4f itd.

21. **Multi-file comparison / overlay**  
    Porownanie DFT/phase dla kilku plikow, sezonow lub pasm.

## Kolejnosc wdrazania

Rekomendowana praktyczna kolejnosc:

1. log-scale DFT
2. Nyquist indicator
3. spectral window
4. improved frequency errors
5. local noise + adaptive S/N
6. Lomb-Scargle
7. FAP
8. FITS import
9. phase colored by epoch
10. harmonic suggestion
11. BLS
12. barycentric corrections
13. echelle
14. period-spacing search
15. O-C
16. PDM/AOV
17. multi-file comparison
18. MAST integration

## Notatki implementacyjne dla repo

Miejsca, ktore najpewniej beda dotykane przy implementacji:

- `src/lcview/core/periodogram.py`
  - nowe backendy (`lombscargle`, ew. `bls`, pozniej `pdm/aov`),
  - local noise,
  - adaptive S/N,
  - spectral window.

- `src/lcview/core/results.py`
  - poprawa wzoru na `frequency_error`,
  - ewentualnie lepsze raportowanie niepewnosci.

- `src/lcview/core/session.py`
  - nowe ustawienia sesji: log scale, Nyquist line, FAP method, LS/BLS options, time-standard metadata.

- `src/lcview/core/lightcurve.py`
  - FITS loader,
  - ewentualne wsparcie dla bardziej zlozonych metadanych czasu.

- `src/lcview/ui/main_window.py`
  - checkboxy, comboboxy, skroty klawiszowe, nowe akcje i ostrzezenia.

- `src/lcview/ui/plots.py`
  - log y-axis,
  - dodatkowe overlaye i nowe style wizualizacji.

- `src/lcview/ui/results_panel.py`
  - CSV juz istnieje,
  - warto rozszerzyc eksport o formaty przydatne do publikacji.

- `src/lcview/core/phase.py`
  - phase plot colored by epoch bedzie wymagac niesienia informacji o czasie do warstwy wykresu.

## Czego nie priorytetyzowac od razu

Na samym poczatku lepiej **nie** zaczynac od:

- pelnej integracji `MAST` / `astroquery`,
- zlozonego multiband / multi-engine GUI,
- zaawansowanych correctors w stylu `CBV`, `PLD`, `SFF`,
- bardzo specjalistycznych modulow bez wczesniejszego domkniecia statystyki i I/O.

To ma sens dopiero wtedy, gdy podstawowy workflow:

- dobrze liczy istotnosc pikow,
- dobrze pokazuje aliasy i szum,
- dobrze wczytuje nowoczesne dane,
- daje wiarygodny i publikowalny output.

## Zrodla

### Dokumentacja i narzedzia

- Astropy Lomb-Scargle: https://docs.astropy.org/en/stable/timeseries/lombscargle.html
- Astropy BLS: https://docs.astropy.org/en/stable/timeseries/bls.html
- Astropy TimeSeries: https://docs.astropy.org/en/stable/timeseries/index.html
- Astropy Time / barycentric corrections: https://docs.astropy.org/en/stable/time/index.html
- Lightkurve: https://lightkurve.github.io/lightkurve/
- Lightkurve correctors: https://lightkurve.github.io/lightkurve/reference/correctors.html
- VStar overview: https://www.aavso.org/vstar-overview
- Period04: https://www.period04.net/
- Period04 changelog: https://period04.net/changelog-1293.html

### Publikacje i materialy naukowe

- VanderPlas 2018, *Understanding the Lomb-Scargle Periodogram*: https://arxiv.org/abs/1703.09824
- VanderPlas & Ivezic 2015, *Periodograms for Multiband Astronomical Time Series*: https://arxiv.org/abs/1502.01344
- Montgomery & O'Donoghue 1999 - klasyczna referencja dla frequency uncertainty w asterosejsmologii

### Wniosek z przegladu

Najlepsza strategia dla `lcView` to:

1. nie przepisywac obecnego prewhitening core,
2. dobudowac mocniejsza statystyke,
3. poprawic wizualizacje widma,
4. dodac lepsze I/O dla FITS i czasu astronomicznego,
5. dopiero potem inwestowac w najbardziej zaawansowane moduly naukowe.
