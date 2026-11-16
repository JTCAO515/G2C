"""Signed local-only selection-source -> Source4 -> original sole writer proof.

Every fixture page is ok/nonempty with an unmatched observed Chinese name. No
provider outcome is rewritten; final checks/transaction rollback stay genuine.
"""
from unittest.mock import patch

import rich_publication_pg as existing
from cj_draft.rich_place_selection import RichPlaceSelectionContextSource,LioSelectedRichPublisher


def exercise(root,conninfo):
    existing.exercise(root,conninfo,source_type=RichPlaceSelectionContextSource,
                      publisher_type=LioSelectedRichPublisher,provider_available=True)


def main():
    with patch.object(existing.native,'exercise',exercise):existing.native.main()


if __name__=='__main__':main()
