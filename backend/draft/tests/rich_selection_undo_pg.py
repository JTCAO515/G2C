"""Reuse the actual signed two-plans/append-only undo harness with new v2 basis.

Only the C source/publisher are explicitly opted in. HTTP/PG remain private
fixtures; this neither installs the L host nor grants any real-service window.
"""
from unittest.mock import patch

import rich_undo_pg as existing
from cj_draft.rich_place_selection import RichPlaceSelectionContextSource,LioSelectedRichPublisher


def main():
    with patch.object(existing,'RichProviderContextSource',RichPlaceSelectionContextSource), \
            patch.object(existing,'LioRichPublisher',LioSelectedRichPublisher):
        existing.main()


if __name__=='__main__':main()
