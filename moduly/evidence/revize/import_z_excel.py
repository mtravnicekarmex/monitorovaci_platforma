import pandas as pd
from pathlib import Path
from icecream import ic
# from sqlalchemy.orm import Session
# from moduly.evidence.revize.database.models import Revize
# from moduly.evidence.revize.mapping_excel_vs_db import REVIZE_MAPPING_ROWS, REVIZE_MAPPING_COLUMNS


# Set options for pandas display
pd.set_option('display.max_rows', 1000)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.reset_option('display.float_format')


excel_path = Path(r"P:\Holding\Správa Majetku\Budovy\F\Revize\Revize F.xlsx")

df = pd.read_excel(excel_path, sheet_name="F revize")


ic(df.columns)
ic(df)

