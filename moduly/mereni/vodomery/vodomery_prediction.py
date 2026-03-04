from sqlalchemy import text
from core.db.connect import get_session_pg


def rebuild_profiles(model_version: int = 1):
    """
    Full rebuild baseline profilů pro všechna odběrná místa.
    Používá robustní MAD std.
    """

    session = get_session_pg()

    try:
        # 1️⃣ smažeme staré profily této verze
        session.execute(
            text("""
                DELETE FROM monitoring.vodomery_anomaly_profiles
                WHERE model_version = :model_version
            """),
            {"model_version": model_version},
        )

        # 2️⃣ výpočet statistik
        session.execute(
            text("""
            WITH base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = false
                    AND platne = true
                    AND reset_detected = false
                    AND delta IS NOT NULL
            ),
            stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    avg(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    COUNT(*) AS sample_size
                FROM base
                GROUP BY
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot
            ),
            mad AS (
                SELECT
                    b.identifikace,
                    b.interval_minutes,
                    b.day_of_week,
                    b.slot,
                    percentile_cont(0.5)
                        WITHIN GROUP (ORDER BY abs(b.delta - s.median))
                        AS mad
                FROM base b
                JOIN stats s USING (identifikace, interval_minutes, day_of_week, slot)
                GROUP BY
                    b.identifikace,
                    b.interval_minutes,
                    b.day_of_week,
                    b.slot
            )
            INSERT INTO monitoring.vodomery_anomaly_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                p10,
                p90,
                std,
                model_version,
                sample_size
            )
            SELECT
                s.identifikace,
                s.interval_minutes,
                s.day_of_week,
                s.slot,
                s.median,
                s.mean,
                s.p10,
                s.p90,
                GREATEST(1.4826 * COALESCE(m.mad, 0.0), 0.0001) AS std,
                :model_version,
                s.sample_size
            FROM stats s
            LEFT JOIN mad m
                USING (identifikace, interval_minutes, day_of_week, slot)
            """),
            {"model_version": model_version},
        )

        session.commit()
        print(f"Profiles rebuild complete (model_version={model_version})")

    finally:
        session.close()

