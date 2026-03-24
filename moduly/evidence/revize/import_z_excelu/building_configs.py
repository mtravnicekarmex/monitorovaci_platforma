from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExcelColumnConfig:
    datum: str
    interval: str
    jednotka_platnosti: str
    dodavatel: str
    soubor_columns: tuple[str, ...]
    servisni_smlouva: str
    fid: str
    typ_zarizeni: str
    nazev_revize_source: str
    nazev_revize_detail: str | None = None


@dataclass(frozen=True)
class BuildingImportConfig:
    budova: str
    excel_file: Path
    revize_base_dir: Path
    nazev_revize_prefix: str
    columns: ExcelColumnConfig
    extractor_name: str = "simple"
    excel_header_row: int = 1


BUILDING_CONFIGS = {
    "F": BuildingImportConfig(
        budova="F",
        excel_file=Path(r"P:\Holding\Správa Majetku\Budovy\F\Revize\Revize F.xlsx"),
        revize_base_dir=Path(r"P:\Holding\Správa Majetku\Budovy\F\Revize"),
        nazev_revize_prefix="F - revize",
        extractor_name="simple",
        columns=ExcelColumnConfig(
            datum="termín provedení:",
            interval="interval",
            jednotka_platnosti="Unnamed: 6",
            dodavatel="firma",
            soubor_columns=("revize",),
            servisni_smlouva="servisní smlouva",
            fid="Unnamed: 16",
            typ_zarizeni="typ_zarizeni",
            nazev_revize_source="F revize",
            nazev_revize_detail="Unnamed: 2",
        ),
    ),

    "G": BuildingImportConfig(
        budova="G",
        excel_file=Path(r"P:\Holding\Správa Majetku\Budovy\G\Revize\Revize G.xlsx"),
        revize_base_dir=Path(r"P:\Holding\Správa Majetku\Budovy\G\Revize"),
        nazev_revize_prefix="G - revize",
        extractor_name="g_multi_revision",
        columns=ExcelColumnConfig(
            datum="termín provedení:",
            interval="interval",
            jednotka_platnosti="Unnamed: 6",
            dodavatel="firma",
            soubor_columns=("revize", "Unnamed: 9"),
            servisni_smlouva="servisní smlouva",
            fid="Unnamed: 17",
            typ_zarizeni="typ_zarizeni",
            nazev_revize_source="G revize",
            nazev_revize_detail="Unnamed: 2",
        ),
    ),
}
