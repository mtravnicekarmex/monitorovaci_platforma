from datetime import timedelta
import math
from pathlib import Path

import pandas as pd









def load_excel(config):
    df = pd.read_excel(config.excel_file, header=config.excel_header_row)
    rename_map = {}
    existing_columns = set(df.columns)
    columns = config.columns

    aliases = {
        columns.datum: "datum",
        columns.interval: "interval",
        columns.jednotka_platnosti: "jednotka_platnosti",
        columns.dodavatel: "dodavatel",
        columns.servisni_smlouva: "servisni_smlouva",
        columns.fid: "fid",
        columns.typ_zarizeni: "typ_zarizeni",
        columns.nazev_revize_source: "nazev_revize_source",
    }
    for index, source in enumerate(columns.soubor_columns, start=1):
        aliases[source] = f"soubor_{index}"
    if columns.nazev_revize_detail:
        aliases[columns.nazev_revize_detail] = "nazev_revize_detail"

    for source, target in aliases.items():
        if source not in existing_columns:
            continue
        if target in existing_columns and source != target:
            continue
        rename_map[source] = target

    if rename_map:
        df = df.rename(columns=rename_map)

    return df


def normalize_date(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "date"):
        return value.date()
    return value


def normalize_soubor_path(soubor, revize_base_dir: Path):
    path = Path(soubor)
    if path.is_absolute():
        return str(path)
    return str(revize_base_dir / path)


def get_row_value(row, column):
    value = row[column]
    if isinstance(value, pd.Series):
        non_empty = value[value.notna()]
        if non_empty.empty:
            return None
        return non_empty.iloc[0]
    if pd.isna(value):
        return None
    return value


def parse_fid_list(fid_cell):
    if pd.isna(fid_cell):
        return []

    result = []
    for value in str(fid_cell).split(","):
        value = value.strip()
        if value.isdigit():
            result.append(int(value))
    return result


def compute_platnost(datum, delka):
    if pd.isna(datum):
        return None
    return datum + timedelta(days=365 * float(delka))


def parse_delka_platnosti(row):
    value = float(get_row_value(row, "interval"))
    unit = str(get_row_value(row, "jednotka_platnosti") or "").strip().lower()
    if unit.startswith("měs") or unit.startswith("mes"):
        return value / 12
    return value


def years_to_db_value(years):
    if math.isclose(years, round(years)):
        return int(round(years))
    return years


def add_nazev_revize(df, config):
    df = df.copy()
    source_column = "nazev_revize_source" if "nazev_revize_source" in df.columns else "nazev_revize"
    # Nazev hlavni skupiny se v Excelu nekdy uvede jen na prvnim radku bloku.
    main_value = df[source_column].ffill() if source_column in df.columns else pd.Series(index=df.index, dtype="object")
    detail_value = df["nazev_revize_detail"] if "nazev_revize_detail" in df.columns else pd.Series(index=df.index, dtype="object")

    def compose_name(main, detail):
        if pd.isna(main):
            return None

        parts = [config.nazev_revize_prefix, str(main).strip()]
        if pd.notna(detail):
            detail_text = str(detail).strip()
            if detail_text:
                parts.append(detail_text)
        return " - ".join(parts)

    df["nazev_revize"] = [
        compose_name(main, detail)
        for main, detail in zip(main_value, detail_value)
    ]
    return df


def build_record(row, config):
    primary_soubor = get_row_value(row, "soubor_1")
    datum = normalize_date(get_row_value(row, "datum"))
    delka = parse_delka_platnosti(row)
    return {
        "budova": config.budova,
        "datum": datum,
        "delka_platnosti": years_to_db_value(delka),
        "datum_platnosti": normalize_date(compute_platnost(datum, delka)),
        "typ_zarizeni": get_row_value(row, "typ_zarizeni"),
        "nazev_revize": get_row_value(row, "nazev_revize"),
        "dodavatel": get_row_value(row, "dodavatel"),
        "soubor": normalize_soubor_path(primary_soubor, config.revize_base_dir),
        "servisni_smlouva": get_row_value(row, "servisni_smlouva"),
        "fid_list": parse_fid_list(get_row_value(row, "fid")),
    }


def build_record_with_values(row, config, soubor, fid_list):
    record = build_record(row, config)
    record["soubor"] = normalize_soubor_path(soubor, config.revize_base_dir)
    record["fid_list"] = fid_list
    return record


def extract_simple_records(config):
    df = load_excel(config)
    df = df.dropna(subset=["datum"]).copy()
    df = add_nazev_revize(df, config)
    return [build_record(row, config) for _, row in df.iterrows()], []


def split_fid_groups(fid_value):
    if fid_value is None or pd.isna(fid_value):
        return []

    groups = [part.strip() for part in str(fid_value).split(" - ")]
    return [parse_fid_list(group) for group in groups if group]


def get_soubor_values(row):
    soubor_values = []
    index = 1
    while f"soubor_{index}" in row.index:
        value = get_row_value(row, f"soubor_{index}")
        if value:
            soubor_values.append(value)
        index += 1
    return soubor_values


def extract_g_multi_revision_records(config):
    df = load_excel(config)
    df = df.dropna(subset=["datum"]).copy()
    df = add_nazev_revize(df, config)

    records = []
    warnings = []

    for _, row in df.iterrows():
        soubor_values = get_soubor_values(row)
        fid_groups = split_fid_groups(get_row_value(row, "fid"))

        if len(soubor_values) > 1:
            if fid_groups and len(fid_groups) != len(soubor_values):
                warnings.append(
                    f"{config.budova}: '{get_row_value(row, 'nazev_revize')}' has {len(soubor_values)} files but {len(fid_groups)} fid groups"
                )

            for index, soubor in enumerate(soubor_values):
                fid_list = fid_groups[index] if index < len(fid_groups) else []
                records.append(build_record_with_values(row, config, soubor, fid_list))
            continue

        records.append(build_record(row, config))

    return records, warnings


EXTRACTORS = {
    "simple": extract_simple_records,
    "g_multi_revision": extract_g_multi_revision_records,
}


def extract_records(config):
    extractor = EXTRACTORS.get(config.extractor_name)
    if extractor is None:
        raise ValueError(f"Unknown extractor '{config.extractor_name}' for building {config.budova}")
    return extractor(config)
