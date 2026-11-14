#if os(iOS)
import CJTripClient
import SwiftUI

/// User-facing controls over the existing read-only MapKit canvas.
public struct LioRecordedTripMap: View {
    private let places: Result<[TripPlaceProjection], any Error>
    private let language: ShellLanguage
    @State private var expanded = false
    @State private var unavailable = false

    public init(document: StructuredTripDocument, language: ShellLanguage) {
        places = Result { try TripPlaceProjection.read(from: document) }
        self.language = language
    }

    public var body: some View {
        switch places {
        case .failure:
            Text(language.text("Map unavailable", "暂时无法显示地图"))
                .accessibilityIdentifier("lio.trip.recorded-map.unavailable")
        case .success(let places):
            if places.contains(where: { $0.markerCoordinate != nil }) {
                VStack(alignment: .leading, spacing: 8) {
                    Button(expanded ? language.text("Hide map", "收起地图") : language.text("Show map", "在地图上看")) {
                        expanded.toggle()
                        unavailable = false
                    }
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("lio.trip.recorded-map")
                    Text(language.text("Viewing the map sends its area to Apple.", "查看地图时，Apple 会收到地图显示区域。"))
                        .font(.footnote)
                    if expanded {
                        RecordedPlaceMap(places: places, language: language, failed: { unavailable = true }, showsSourceDetails: false)
                            .frame(height: 320)
                        if unavailable {
                            Text(language.text("Map unavailable", "暂时无法显示地图"))
                .accessibilityIdentifier("lio.trip.recorded-map.unavailable")
                        }
                        Link(language.text("Apple Maps legal information", "Apple 地图法律信息"),
                             destination: URL(string: "https://www.apple.com/legal/internet-services/maps/")!)
                            .frame(minHeight: 44)
                    }
                }
            }
        }
    }
}
#endif
