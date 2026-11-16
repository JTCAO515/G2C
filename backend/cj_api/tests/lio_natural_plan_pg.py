"""Frozen natural direct controls with ordinary prefixed traveler answers.

The native API retains each original body/MID/hash. Actual registered profile
extraction precedes defaults and source issuance; the same qualified account
counts that extra model. All supplier transports remain local fixtures.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
from lio_qualified_pipeline_pg import main


if __name__=='__main__':main(natural_direct=True)
