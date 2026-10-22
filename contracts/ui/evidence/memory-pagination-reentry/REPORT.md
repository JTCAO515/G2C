# CJ006 Memory pagination callback repair

Independent Testing input: CJ-006-memory-container/CONTAINER-REPORT.md, pagination-reentry.log and its snapshot IndependentMemoryPaginationReentryTests.swift, all read before repair. Base for this delta4604b79fd2afee140ce4c2ae73c07383827580ff; prior Memory40cc, Trip4604, pin and clear evidence retained.

Reproduced old more=true action: accepts checked epoch, hasMore called currentBinding again, callback selected a current item, then old pagination minted a new epoch/cleared itemID/dispatched GET. Source repair is one final accepts(context) check after hasMore and before any mutation. accepts itself checks binding/epoch/busy after its callback returns, so callback reentry during that final check is also fenced. No domain/API/selection authority change.

Adapted the exact independent test to parameterize binding callback positions1,2,3 and route detail responses by actual operation, adding a successful canonical selected-detail assertion. Before: positions2/3 FAIL with7 assertions overall; position1 is the existing safe negative control. After: all3 positions PASS, old pagination sends no third list request, and the new item's detail GET loads item a. Canonical data and requests remain intercepted synthetic records.

PASS:10 functions across IndependentMemoryPaginationReentryTests1 + existing MemoryContainerHostTests9 (`after.txt`). Previous91/full module and20 pin positive evidence are reused, not rerun to imply coverage. No iOS-only view change; this Swift source compiled in the actual package test. A later final iOS compile with typed clear will include this same source.

No production POST, live HTTP, Keychain, account, device, signing, permission or domain edit. Author repair does not automatically lift independent40cc HOLD. Account clear's separate same-tuple regression remains failing until typed settlement consumption; Trip producer12df/source4604 gate is separate.

Command: established cache environment, swift test --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution --filter 'IndependentMemoryPaginationReentryTests|MemoryContainerHostTests'.
