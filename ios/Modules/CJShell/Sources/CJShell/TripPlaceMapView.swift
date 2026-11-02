#if os(iOS)
import SwiftUI
import MapKit
import CJTripClient
import CJRunClient

struct TripPlaceMapView: View {
    let document: StructuredTripDocument
    let language: ShellLanguage
    @State private var expanded = false
    @State private var failed = false
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            switch projection {
            case .failure:
                RunReadableText(text: language.text("Place sources unavailable. The text itinerary remains readable.", "地点来源不可读取，文字行程仍可阅读。"))
            case .success(let places):
                if places.isEmpty {
                    RunReadableText(text: language.text("No recorded places; no map markers.", "没有地点来源记录，不补地图标记。")).accessibilityIdentifier("trip.map.empty")
                } else {
                    ForEach(places) { place in
                        VStack(alignment: .leading, spacing: 6) {
                            RunSelectableText(text: place.nameZH).accessibilityIdentifier("trip.map.name." + place.id)
                            RunSelectableText(text: place.provider + " · " + place.providerID).accessibilityLabel(language.text("Original provider and place identifier","原来源及地点标识")).accessibilityValue(place.provider + " · " + place.providerID).accessibilityIdentifier("trip.map.identity." + place.id)
                            RunSelectableText(text: place.addressZH.value ?? language.text("Address UNKNOWN", "地址 UNKNOWN")).accessibilityIdentifier("trip.map.address." + place.id)
                            if language == .english {
                                RunSelectableText(text: place.officialNameEN.value ?? "Official English name UNKNOWN")
                                RunSelectableText(text: place.officialAddressEN.value ?? "Official English address UNKNOWN")
                            }
                            RunSelectableText(text: (place.rawCoordinate ?? "UNKNOWN") + " · " + (place.crs ?? "UNKNOWN"))
                                .accessibilityLabel(language.text("Original coordinate declaration","原坐标声明")).accessibilityValue((place.rawCoordinate ?? "UNKNOWN") + " · " + (place.crs ?? "UNKNOWN"))
                                .accessibilityIdentifier("trip.map.coordinate." + place.id)
                            RunReadableText(text: place.evidenceLevel + " · pending · " + (place.markerCoordinate == nil ? language.text("Location needs verification; no marker", "位置待核实，不画点") : language.text("Recorded coordinates; physical alignment unverified", "来源坐标，实际点位对齐未核实")))
                                .accessibilityIdentifier("trip.map.status." + place.id)
                        }
                    }
                    if places.contains(where: { $0.markerCoordinate != nil }) {
                        Button { expanded.toggle() } label: {
                            RunReadableText(text: expanded ? language.text("Hide map", "收起地图") : language.text("Show Apple map", "显示 Apple 地图"))
                                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
                        }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("trip.map.show")
                        RunReadableText(text: language.text("Viewing the map sends its region to Apple. Your location is not requested. Text remains available if map tiles fail.", "查看地图会向 Apple 发送查看区域，不申请你的位置。地图瓦片失败时仍可阅读文字。"), style: .caption)
                        if expanded {
                            RecordedPlaceMap(places: places, language: language, failed: { failed = true })
                                .frame(height: 320).accessibilityIdentifier("trip.map.canvas")
                            Link(destination: URL(string:"https://www.apple.com/legal/internet-services/maps/")!) {
                                RunReadableText(text:language.text("Apple Maps legal information","Apple 地图法律信息")).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
                            }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("trip.map.legal")
                        }
                        if failed {
                            RunReadableText(text: language.text("Map unavailable. Use the recorded names and addresses above.", "地图暂不可用，请使用上方来源名称和地址。"))
                                .accessibilityIdentifier("trip.map.unavailable")
                        }
                    }
                }
            }
        }.accessibilityElement(children: .contain).accessibilityIdentifier("trip.map.sources")
    }
    private var projection: Result<[TripPlaceProjection], any Error> {
        Result { try TripPlaceProjection.read(from: document) }
    }
}

private final class RecordedPlaceAnnotation: NSObject, MKAnnotation {
    let place: TripPlaceProjection
    let coordinate: CLLocationCoordinate2D
    var title: String? { place.nameZH }
    var subtitle: String? { place.providerID + " · " + place.rawCoordinate! }
    init(place: TripPlaceProjection, coordinate: PlaceCoordinateV1) {
        self.place = place
        // Representation for MapKit only; source strings remain verbatim. No CRS conversion.
        self.coordinate = .init(latitude: NSDecimalNumber(decimal: coordinate.latitude.value).doubleValue,
                                longitude: NSDecimalNumber(decimal: coordinate.longitude.value).doubleValue)
    }
}

private struct RecordedPlaceMap: UIViewRepresentable {
    let places: [TripPlaceProjection]
    let language: ShellLanguage
    let failed: () -> Void
    func makeUIView(context: Context) -> RecordedMapCanvas { RecordedMapCanvas() }
    func updateUIView(_ map: RecordedMapCanvas, context: Context) { map.configure(places:places,language:language,failed:failed) }
    static func dismantleUIView(_ map: RecordedMapCanvas, coordinator: ()) { map.retire() }
}

/// A read-only native MapKit image with accessible original-source markers.
/// MapKit supplies the image and projection; no image cropping, persistence,
/// source reconstruction, location access or custom CRS transform is performed.
private final class RecordedMapCanvas: UIView {
    private let imageView = UIImageView()
    private var markers: [UIButton] = []
    private var annotations: [RecordedPlaceAnnotation] = []
    private var operation: MKMapSnapshotter?
    private var signature: String?
    private var size: CGSize = .zero
    private var failed: (() -> Void)?
    private var retired = false
    private var zoomFactor = 1.0
    private let zoomIn = UIButton(type:.system)
    private let zoomOut = UIButton(type:.system)
    override init(frame: CGRect) {
        super.init(frame:frame)
        imageView.isAccessibilityElement = false
        imageView.contentMode = .scaleToFill
        addSubview(imageView)
        for (button,symbol,factor) in [(zoomIn,"plus.magnifyingglass",0.5),(zoomOut,"minus.magnifyingglass",2.0)] {
            button.setImage(UIImage(systemName:symbol),for:.normal)
            button.tintColor = .label;button.backgroundColor = .systemBackground;button.layer.cornerRadius=8
            button.addAction(UIAction { [weak self] _ in
                guard let self,!self.retired else { return }
                self.zoomFactor *= factor;self.load()
            },for:.touchUpInside)
            addSubview(button)
        }
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) is unavailable") }
    func configure(places:[TripPlaceProjection],language:ShellLanguage,failed:@escaping ()->Void) {
        let next=places.map { $0.id+":"+$0.snapshotSHA256 }.joined(separator:"|")+language.rawValue
        guard signature != next else { return }
        retired=false;signature=next;self.failed=failed
        zoomFactor=1
        zoomIn.accessibilityLabel=language.text("Zoom in","放大地图")
        zoomOut.accessibilityLabel=language.text("Zoom out","缩小地图")
        annotations=places.compactMap { p in p.markerCoordinate.map { RecordedPlaceAnnotation(place:p,coordinate:$0) } }
        size = .zero;setNeedsLayout()
    }
    override func layoutSubviews() {
        super.layoutSubviews();imageView.frame=bounds
        zoomIn.frame=CGRect(x:bounds.width-52,y:8,width:44,height:44)
        zoomOut.frame=CGRect(x:bounds.width-52,y:60,width:44,height:44)
        guard !retired,bounds.width>0,bounds.height>0,size != bounds.size else { return }
        size=bounds.size;load()
    }
    func retire() {
        retired=true;signature=nil;operation?.cancel();operation=nil
        imageView.image=nil;markers.forEach { $0.removeFromSuperview() };markers=[];annotations=[];failed=nil
    }
    private func load() {
        operation?.cancel();markers.forEach { $0.removeFromSuperview() };markers=[];imageView.image=nil
        guard let first=annotations.first else { return }
        var rect=MKMapRect.null
        for annotation in annotations {
            let point=MKMapPoint(annotation.coordinate)
            rect=rect.union(MKMapRect(x:point.x,y:point.y,width:1,height:1))
        }
        if rect.width<10000 || rect.height<10000 {
            let point=MKMapPoint(first.coordinate)
            rect=rect.union(MKMapRect(x:point.x-10000,y:point.y-10000,width:20000,height:20000))
        }
        let options=MKMapSnapshotter.Options();options.size=bounds.size;options.pointOfInterestFilter = .excludingAll
        let padded=rect.insetBy(dx:-rect.width*0.5,dy:-rect.height*0.5)
        options.mapRect=MKMapRect(x:padded.midX-padded.width*zoomFactor/2,y:padded.midY-padded.height*zoomFactor/2,width:padded.width*zoomFactor,height:padded.height*zoomFactor)
        let request=MKMapSnapshotter(options:options);operation=request
        #if DEBUG && targetEnvironment(simulator)
        if ProcessInfo.processInfo.environment["G2C_ACCEPTANCE_MAP_LOADING"] == "synthetic-delegate-failure" {
            Task { @MainActor [weak self,weak request] in
                guard let self,let request,self.operation === request,!self.retired else { return }
                self.failed?()
            }
            return
        }
        #endif
        request.start { [weak self,weak request] snapshot,error in
            guard let self,let request,self.operation === request,!self.retired else { return }
            guard let snapshot,error == nil else { self.failed?();return }
            self.imageView.image=snapshot.image
            for annotation in self.annotations {
                let button=UIButton(type:.system)
                button.setImage(UIImage(systemName:"mappin.circle.fill"),for:.normal)
                button.tintColor = .label;button.backgroundColor = .systemBackground;button.layer.cornerRadius=22
                let point=snapshot.point(for:annotation.coordinate)
                button.frame=CGRect(x:point.x-22,y:point.y-22,width:44,height:44)
                button.accessibilityIdentifier="trip.map.marker."+annotation.place.id
                button.accessibilityLabel=annotation.place.nameZH
                button.accessibilityValue=[annotation.place.providerID,annotation.place.rawCoordinate!,"GCJ-02",String(annotation.coordinate.longitude)+","+String(annotation.coordinate.latitude)].joined(separator:"|")
                button.addAction(UIAction { [weak button] _ in button?.isSelected.toggle() },for:.touchUpInside)
                self.addSubview(button);self.markers.append(button)
            }
            self.bringSubviewToFront(self.zoomIn);self.bringSubviewToFront(self.zoomOut)
        }
    }
}
#endif
