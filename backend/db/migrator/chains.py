"""Append-only core migration chain, assembled from the chain modules."""

from .chain_0001_0021 import CHAIN_0001_0021
from .chain_0022_0041 import CHAIN_0022_0041
from .chain_0046_0060 import CHAIN_0046_0060
from .chain_0056_0070 import CHAIN_0056_0070
from .chain_0069_0083 import CHAIN_0069_0083
from .chain_0075_period_days import CHAIN_0075_PERIOD_DAYS
from .chain_0076_tariff_squad_sync import CHAIN_0076_TARIFF_SQUAD_SYNC
from .engine import Migration

MIGRATIONS: list[Migration] = [
    *CHAIN_0001_0021,
    *CHAIN_0022_0041,
    *CHAIN_0046_0060,
    *CHAIN_0056_0070,
    *CHAIN_0069_0083,
    *CHAIN_0075_PERIOD_DAYS,
    *CHAIN_0076_TARIFF_SQUAD_SYNC,
]
