"""Actual signed API/Memory/registered exits, HTTP fixtures and private PG only."""
from lio_cross_language_pg import main


if __name__=='__main__':
    main(basic_memory=True,fallback_only=True)
    main(basic_memory=True,fallback_only=True,max_steps=1)
