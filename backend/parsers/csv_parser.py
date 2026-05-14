import logging

import pandas as pd

logger = logging.getLogger(__name__)


def parse_csv(file_path: str) -> list[dict]:
    try:
        dataframe = pd.read_csv(file_path)
        initial_rows = len(dataframe)

        duplicate_rows = int(dataframe.duplicated().sum())
        dataframe = dataframe.drop_duplicates()

        stale_rows = 0
        if "days_since_recharge" in dataframe.columns:
            days_since_recharge = pd.to_numeric(dataframe["days_since_recharge"], errors="coerce")
            stale_mask = days_since_recharge > 90
            stale_rows = int(stale_mask.fillna(False).sum())
            dataframe = dataframe.loc[~stale_mask.fillna(False)]

        else:
            logger.warning("Column 'days_since_recharge' not found — stale row filter skipped")
        
        dropped_rows = initial_rows - len(dataframe)
        logger.info(
            "CSV cleaned from %s to %s rows; dropped %s rows total (%s duplicate rows, %s stale rows)",
            initial_rows,
            len(dataframe),
            dropped_rows,
            duplicate_rows,
            stale_rows,
        )

        return dataframe.to_dict(orient="records")
    except Exception as exc:
        raise RuntimeError(f"Failed to parse CSV file '{file_path}': {exc}") from exc