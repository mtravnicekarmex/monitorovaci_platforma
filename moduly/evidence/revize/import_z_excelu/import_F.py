import logging

from core.db.connect import ENGINE_PG

from moduly.evidence.revize.import_z_excelu.building_configs import BUILDING_CONFIGS
from moduly.evidence.revize.import_z_excelu.import_common import import_excel_to_db


CONFIG = BUILDING_CONFIGS["F"]
LOGGER = logging.getLogger(__name__)


if __name__ == "__main__":
    LOGGER.info("Starting import for building %s", CONFIG.budova)
    stats = import_excel_to_db(CONFIG, db_engine=ENGINE_PG)
    print(stats)
