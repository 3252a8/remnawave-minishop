"""Append-only core migration chain, assembled from the chain modules."""

from .chain_0001_0021 import CHAIN_0001_0021
from .chain_0022_0041 import CHAIN_0022_0041
from .chain_0046_0060 import CHAIN_0046_0060
from .engine import Migration

MIGRATIONS: list[Migration] = [*CHAIN_0001_0021, *CHAIN_0022_0041, *CHAIN_0046_0060]
