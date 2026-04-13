# Konverzace 2026-04-10 - vodomery

## Kontext
- Repo: `C:\Users\tra\Desktop\tra\Python\PycharmProjects\monitorovaci_platforma_v1.5`
- Tema: predikce spotreby vodomeru, modely `v1` a `v2`, weekly model selection pipeline, quarter-hour outlier handling

## Chronologie
1. Byla provedena revize modulu pro predikci spotreby vodomeru a chovani 2 modelu.
   Zaver:
   `v1` byl jediny skutecne aktivni model v runtime.
   `v2` byl implementovany jen castecne a nebyl konzistentne napojen do scheduleru a API.

2. Byl navrzen a implementovan novy weekly pipeline:
   `rebuild_profiles` bezi 1x tydne.
   Trening bere poslednich `120` dni bez posledniho tydne.
   Posledni tyden je validacni okno.
   Vsechny kandidatni modely se porovnaji.
   Na dalsi tyden se nasadi presnejsi model.
   Po rebuildu se posila email report s vysledky modelu.

3. Provedene zmeny v kodu:
   - Generalizovany vyber kandidatu a aktivniho modelu v `moduly/mereni/vodomery/vodomery_prediction.py`
   - Persistencni tabulky pro selection run a candidate vysledky v `moduly/mereni/vodomery/database/models.py`
   - Helpery pro aktivni model v `moduly/mereni/vodomery/database/model_validation.py`
   - Report email v `moduly/mereni/vodomery/reporting/model_rebuild_report.py`
   - Scheduler upraven tak, ze:
     `weekly_job` vola rebuild + report
     `quarter_hour_job` scoreuje vsechny kandidatni modely, ale alerting posila jen pro aktivni model
   - API sluzby pro vodomery jsou version-aware a ctou data podle aktivniho modelu
   - Doplneny testy scheduleru a prediction flow

4. Runtime overeni:
   - `rebuild_profiles()` probehl uspesne
   - vznikl `selection_run_id = 1`
   - aktivni model po vyhodnoceni: `v2`
   - report email byl odeslan uspesne

5. Kontrola validacnich metrik posledniho behu:
   - okno treninku:
     `2025-12-11 13:17:32` az `2026-04-03 13:17:32`
   - okno validace:
     `2026-04-03 13:17:32` az `2026-04-10 13:17:32`
   - `v1`:
     `validation_total_count=37763`
     `coverage=1.0`
     `MAE=1.155032`
     `RMSE=77.785363`
     `bias=-0.458827`
   - `v2`:
     `validation_total_count=37763`
     `coverage=1.0`
     `MAE=1.147665`
     `RMSE=73.842478`
     `bias=-0.451669`
   - `v2` vyhral korektne

6. Pri analyze `v2` byly nalezeny outliery, ktere tahly RMSE:
   - `E_V4`
   - `E_V2`
   - `E_V5`
   - `A_V3`

7. Na zaklade dalsiho pozadavku bylo rozhodnuto resit outliery driv, uz pri `quarter_hour_job`.
   To bylo implementovano v importni pipeline vodomeru, ne az ve scoringu.

## Posledni provedene zmeny
- V `moduly/mereni/vodomery/database/vodomery_db_vse.py` byl doplnen konzervativni outlier filtr nad `delta`:
  - pracuje nad recentni validni historii zarizeni
  - extremni mereni oznaci jako `platne=False`
  - takove mereni dostane `delta=None`
  - invalidni outlier neposune baseline pro dalsi vypocet `delta`
  - stejne pravidlo plati i pro gap-fill pripady

- V `services/api/services/vodomery.py` bylo doplneno:
  - vraceni flagu `platne` v measurement series
  - v branch/day vypoctech se `platne=False` nuluj e ze spotreby

- V dashboardu bylo doplneno:
  - `moduly/apps/dashboard/vodomery_shared.py`
  - `moduly/apps/dashboard/pages/2_vodomery.py`
  - `moduly/apps/dashboard/pages/5_vodomery_detail.py`
  Invalidni mereni se nezapocitavaji do spotreby ani kumulaci.

- Doplneny testy:
  - `tests/test_vodomery_db_import.py`
  - rozsireni `tests/test_vodomery_service.py`

## Overeni poslednich zmen
- `python -m py_compile ...` proslo
- rucni smoke test helperu pros el
- `pytest` nesel spustit, protoze v prostredi chybi balicek `pytest`

## Dulezity aktualni stav
- Aktivni model po poslednim weekly vyberu: `v2`
- Weekly rebuild/report flow je funkcni
- Quarter-hour pipeline ted umi zastavit outliery pred scoringem a eventy

## Navazani priste
- Rozumny dalsi krok je spustit na aktualnich datech `vodomery_db_import()` nebo cely `quarter_hour_job()` a zkontrolovat:
  - kolik radku bylo oznaceno jako outlier
  - kterych zarizeni se to tyka
  - jestli se zlepsily error metriky hlavne u `E_V4`, `E_V2`, `E_V5`, `A_V3`
