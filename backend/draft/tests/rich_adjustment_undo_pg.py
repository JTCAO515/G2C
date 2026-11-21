"""Signed C adjustment publisher, original receipt and undo on private PG."""
from functools import partial
from unittest.mock import patch

import rich_undo_pg as existing
from cj_draft.rich_place_selection import RichPlaceSelectionContextSource, LioSelectedRichPublisher


if __name__=='__main__':
    exercise=partial(existing.exercise,scoped=True)
    with patch.object(existing,'RichProviderContextSource',RichPlaceSelectionContextSource), \
            patch.object(existing,'LioRichPublisher',LioSelectedRichPublisher), \
            patch.object(existing.native,'exercise',exercise):
        existing.native.main()
