#if os(iOS)
import SwiftUI

/// The one "show the driver" card: the Chinese name large, the Chinese address under it, the English name small.
/// It takes plain text, so a station or airport without coordinates can use it without a made-up location.
/// The screen stays awake while it is shown. Taxi, trip, hotel, roadbook and transport cards all present this view.
/// It is the driver kind of show card (#1572): `LioShowCardSheet` draws it.
struct LioDriverSign: View {
    let language: LioLanguage
    let nameZH: String
    var nameEN: String?
    var addressZH: String?
    /// An optional Chinese request above the name, such as 请送我到这个火车站.
    var requestZH: String?
    /// Accessibility identifiers are `<prefix>.request`, `<prefix>.name`, `<prefix>.address` and `<prefix>.done`.
    var identifierPrefix = "lio.driver"

    var body: some View {
        LioShowCardSheet(language: language,
                         content: .driver(nameZH: nameZH, nameEN: nameEN, addressZH: addressZH, requestZH: requestZH),
                         title: language.text("Show the driver", "给司机看"), identifierPrefix: identifierPrefix)
    }
}
#endif
