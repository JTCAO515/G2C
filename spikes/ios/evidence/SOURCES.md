# Official source provenance

Retrieved 2026-10-21. Tagged manifest copies are adjacent; full resolved revisions are in `../Package.resolved` and Xcode workspace `Package.resolved`. These are source requirements, not lowest-OS runtime acceptance.

| Component | Fixed release / manifest | Manifest platform/toolchain floor |
|---|---|---|
| Supabase Auth | [v2.55.4](https://github.com/supabase/supabase-swift/releases/tag/v2.55.4), [manifest](https://github.com/supabase/supabase-swift/blob/v2.55.4/Package.swift) | iOS 16, macOS 13, Swift tools 6.1; MIT |
| Swift OpenAPI Generator | [1.14.2](https://github.com/apple/swift-openapi-generator/releases/tag/1.14.2), [manifest](https://github.com/apple/swift-openapi-generator/blob/1.14.2/Package.swift) | Host tool macOS 10.15, Swift tools 6.2; generator itself is not an iOS runtime library; Apache 2.0 |
| OpenAPI Runtime | [1.13.3](https://github.com/apple/swift-openapi-runtime/releases/tag/1.13.3), [manifest](https://github.com/apple/swift-openapi-runtime/blob/1.13.3/Package.swift) | iOS 13, macOS 10.15, Swift tools 6.2; Apache 2.0 |
| URLSession transport | [1.3.2](https://github.com/apple/swift-openapi-urlsession/releases/tag/1.3.2), [manifest](https://github.com/apple/swift-openapi-urlsession/blob/1.3.2/Package.swift) | iOS 13, macOS 10.15, Swift tools 6.1; Apache 2.0 |
| Textual | [0.5.0](https://github.com/gonzalezreal/textual/releases/tag/0.5.0), [manifest](https://github.com/gonzalezreal/textual/blob/0.5.0/Package.swift) | iOS 18, macOS 15, Swift tools 6.0; MIT |

Combined candidate needs Swift tools >=6.2 and iOS >=18, subject to the locked transitive graph. Actual tested toolchain Xcode 27.1 (27A9275), Apple Swift 6.4 (swiftlang-6.4.0.34.1); simulator SDK 27.1. This does not establish compatibility with the minimum Swift toolchain or minimum iOS runtime.

Supabase changelog index was fetched and retained as `supabase-changelog-index.md`; no Swift Auth breaking-change item in that index was identified as affecting this compile-only signIn probe. No Auth storage/keychain/session is created. Sources: [official Swift Auth reference](https://supabase.com/docs/reference/swift/auth-signin), [changelog](https://supabase.com/changelog). No database/RLS or real authentication test was run.

Textual 0.5.0 source: `Attachment/AttachmentLoader.swift` defaults image and emoji loaders to network loaders; `Attachment/URLAttachmentLoader.swift` delegates to ImageLoader. The spike overrides both. `StructuredText/StructuredText.swift` uses SwiftUI openURL and Markdown attributed strings; the spike handles all links locally and has no WebView/script engine. Neither remote images nor previews are fetched by the spike's loaders.
