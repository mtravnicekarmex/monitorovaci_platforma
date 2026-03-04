from sqlalchemy import select, insert, update
from sqlalchemy.orm import Session
from moduly.vodomery.database.models import *
from core.db.connect import engine_PG
from app.time_utils import utc_now_naive



def score_new_measurements(model_version: int = 1, batch_size: int = 1000):
    """
    Ultra-efektivní inkrementální scoring (FINÁLNÍ VERZE)

    - PK index scan
    - preload baseline profilů
    - žádné další DB dotazy během loopu
    - bulk insert
    - update scoring state v jedné transakci
    """

    engine = engine_PG()

    with Session(engine, autoflush=False, expire_on_commit=False) as session:

        # -------------------------------------------------
        # 1️⃣ Načti nebo inicializuj scoring state
        # -------------------------------------------------
        state = session.get(VodomeryScoringState, model_version)

        if state is None:
            state = VodomeryScoringState(
                model_version=model_version,
                last_measurement_id=0,
            )
            session.add(state)
            session.commit()

        last_id = state.last_measurement_id

        # -------------------------------------------------
        # 2️⃣ Preload baseline profilů (1 dotaz)
        # -------------------------------------------------
        profiles = session.execute(
            select(VodomeryProfilesAnomaly).where(
                VodomeryProfilesAnomaly.model_version == model_version
            )
        ).scalars().all()

        if not profiles:
            print("No baseline profiles found.")
            return

        profile_cache = {
            (
                p.identifikace,
                p.interval_minutes,
                p.day_of_week,
                p.slot,
            ): p
            for p in profiles
        }

        # -------------------------------------------------
        # 3️⃣ Načti nové measurementy (PK scan)
        # -------------------------------------------------
        measurements = (
            session.query(Mereni_vodomery)
            .filter(
                Mereni_vodomery.id > last_id,
                Mereni_vodomery.synthetic.is_(False),
                Mereni_vodomery.platne.is_(True),
                Mereni_vodomery.reset_detected.is_(False),
                Mereni_vodomery.delta.is_not(None),
            )
            .order_by(Mereni_vodomery.id)
            .limit(batch_size)
            .all()
        )

        if not measurements:
            print("No new measurements to score.")
            return 0

        rows_to_insert = []
        max_processed_id = last_id

        # -------------------------------------------------
        # 4️⃣ Scoring (čistá CPU část)
        # -------------------------------------------------
        for m in measurements:

            key = (
                m.identifikace,
                m.interval_minutes,
                m.day_of_week,
                m.slot,
            )

            profile = profile_cache.get(key)
            if not profile:
                continue

            expected_mean = profile.mean
            expected_std = profile.std if profile.std > 0 else 0.0001
            expected_median = profile.median
            expected_p10 = profile.p10
            expected_p90 = profile.p90

            deviation = m.delta - expected_mean
            z_score = deviation / expected_std

            # kombinovaná detekce
            is_anomaly = (
                m.delta > expected_p90
                or m.delta < expected_p10
                or abs(z_score) >= 3
            )

            if abs(z_score) >= 5:
                severity = "CRITICAL"
            elif abs(z_score) >= 4:
                severity = "HIGH"
            elif abs(z_score) >= 3:
                severity = "MEDIUM"
            else:
                severity = None

            rows_to_insert.append(
                {
                    "measurement_id": m.id,
                    "identifikace": m.identifikace,
                    "date": m.date,
                    "actual_value": m.delta,
                    "expected_mean": expected_mean,
                    "expected_std": expected_std,
                    "expected_median": expected_median,
                    "expected_p10": expected_p10,
                    "expected_p90": expected_p90,
                    "deviation": deviation,
                    "z_score": z_score,
                    "is_anomaly": is_anomaly,
                    "severity": severity,
                    "model_version": model_version,
                }
            )

            max_processed_id = m.id

        # -------------------------------------------------
        # 5️⃣ Jedna transakce
        # -------------------------------------------------
        if rows_to_insert:

            session.execute(
                insert(VodomeryAnomalyScore),
                rows_to_insert,
            )

            session.execute(
                update(VodomeryScoringState)
                .where(VodomeryScoringState.model_version == model_version)
                .values(
                    last_measurement_id=max_processed_id,
                    updated_at=utc_now_naive(),
                )
            )

            session.commit()

            print(
                f"Scored {len(rows_to_insert)} measurements. "
                f"Last processed id: {max_processed_id}"
            )

            return len(rows_to_insert)

        return 0





def backfill_vodomery_scores(model_version: int = 1, batch_size: int = 5000):
    """
    Jednorázové naplnění historických dat.
    Běží dávkově, dokud nejsou všechna data zpracována.
    """

    print(f"Starting backfill for model_version={model_version}")

    total_inserted = 0
    iteration = 0

    while True:
        iteration += 1

        inserted = score_new_measurements(
            model_version=model_version,
            batch_size=batch_size,
        )

        if inserted == 0:
            break

        total_inserted += inserted

        print(
            f"[Batch {iteration}] Inserted: {inserted} | "
            f"Total: {total_inserted}"
        )

    print(
        f"Backfill completed for model_version={model_version}. "
        f"Total inserted: {total_inserted}"
    )


# backfill_vodomery_scores(model_version=1, batch_size=3000)
