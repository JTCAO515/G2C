import SwiftUI

/// Read-only provider facts; no map conversion, location permission, new request,
/// tool retry or TripProposal write is performed by these cards.
public struct PlaceToolTranscriptView: View {
    let transcript: PlaceToolTranscriptV1
    let language: TripLanguage
    public init(transcript: PlaceToolTranscriptV1,language: TripLanguage) { self.transcript = transcript;self.language = language }
    public var body: some View {
        VStack(alignment:.leading,spacing:14) {
            row(language.text("Synthetic local place data · not live provider evidence", "本地合成地点资料 · 非实时供应商证据"),id:"place.origin")
            if transcript.outputs.isEmpty { row(language.text("No complete place result has been received", "尚未收到完整地点结果"),id:"place.pending") }
            ForEach(transcript.outputs.indices,id:\.self) { index in
                result(transcript.outputs[index].result,index:index)
            }
            if let answer = transcript.answer {
                row(language.text("Machine explanation · not official English", "机器说明 · 非官方英文"),id:"place.machine.label")
                row(language == .english ? answer.english : answer.chinese,id:"place.answer")
            }
            if transcript.hasPendingFrame { row(language.text("Incomplete result frame · not displayed as a completed result", "结果片段尚不完整 · 不作为完整结果展示"),id:"place.pendingFrame") }
            row(language.text("Information only. No trip has been saved or changed; future availability is not guaranteed.", "仅供参考，尚未保存或修改行程；不保证未来仍然适用。"),id:"place.noConfirmation")
        }.frame(maxWidth:.infinity,alignment:.leading)
    }
    private func row(_ value: String,id: String) -> some View {
        TripVerificationText(text:value,style:.body).frame(maxWidth:.infinity,alignment:.leading).accessibilityIdentifier(id)
    }
    @ViewBuilder private func result(_ result: PlaceResultV1,index: Int) -> some View {
        let prefix = "place.output.\(index)"
        VStack(alignment:.leading,spacing:10) {
            row(outcome(result.outcome),id:prefix + ".outcome")
            switch result.query {
            case .search(let keyword,let city,let page,_):
                row(language.text("Query: ", "查询：") + keyword + " · " + city + " · " + language.text("Page ","第 ") + String(page),id:prefix + ".query")
            case .detail(let providerID):row(language.text("Requested provider ID: ", "请求的地点 ID：") + providerID,id:prefix + ".query")
            case .route:EmptyView()
            }
            ForEach(result.places.indices,id:\.self) { p in
                let place = result.places[p],id = prefix + "." + place.providerID
                VStack(alignment:.leading,spacing:8) {
                    row(place.nameZH,id:id + ".name")
                    row(language.text("Provider ID: ","地点 ID：") + place.providerID,id:id + ".providerID")
                    observed(place.addressZH,title:language.text("Chinese address", "中文地址"),id:id + ".address") { $0 }
                    observed(place.officialNameEN,title:language.text("Official English name", "官方英文名"),id:id + ".officialName") { $0 }
                    observed(place.officialAddressEN,title:language.text("Official English address", "官方英文地址"),id:id + ".officialAddress") { $0 }
                    coordinate(place.coordinate,title:language.text("POI centre", "地点中心"),id:id + ".centre")
                    coordinate(place.entrance,title:language.text("Entrance", "入口"),id:id + ".entrance")
                    coordinate(place.exit,title:language.text("Exit", "出口"),id:id + ".exit")
                    observed(place.parentID,title:language.text("Parent provider ID", "父地点ID"),id:id + ".parent") { $0 }
                    observed(place.navigationID,title:language.text("Navigation provider ID", "导航地点ID"),id:id + ".navigation") { $0 }
                }.padding(.vertical,8)
            }
            if case .route(let origin,let destination,let mode,let departure) = result.query {
                row(language.text("Route mode: ", "路线方式：") + (mode == "walking" ? language.text("Walking", "步行") : language.text("Driving", "驾车")),id:prefix + ".mode")
                endpoint(origin,title:language.text("Origin", "起点"),id:prefix + ".origin")
                endpoint(destination,title:language.text("Destination", "终点"),id:prefix + ".destination")
                switch departure {
                case .atQueryTime:row(language.text("Departure: at query time", "出发时间：查询时"),id:prefix + ".departure")
                case .specifiedTime(let time):row(language.text("Requested departure: ", "请求出发时间：") + time.iso8601 + " · fold=" + String(time.fold),id:prefix + ".departure")
                }
                ForEach(result.routes.indices,id:\.self) { r in
                    observed(result.routes[r].distance,title:language.text("Distance", "距离"),id:prefix + ".distance") { $0.raw + " " + $0.unit }
                    observed(result.routes[r].duration,title:language.text("Duration", "时长"),id:prefix + ".duration") { $0.raw + " " + $0.unit }
                }
                row(language.text("Provider estimate at query time · future travel not guaranteed", "供应商在查询时的估计 · 不保证未来行程"),id:prefix + ".future")
            }
            if let source = result.source {
                row(language.text("Source: ", "来源：") + source.endpoint,id:prefix + ".source")
                row(language.text("Query started: ", "开始查询：") + source.started.iso8601,id:prefix + ".started")
                row(language.text("Received: ", "接收时间：") + source.received.iso8601,id:prefix + ".received")
                row(language.text("Provider update time: unknown", "供应商更新时间：未知"),id:prefix + ".updated")
            } else { row(language.text("Source: unknown", "来源：未知"),id:prefix + ".source") }
        }
    }
    private func observed<Value>(_ value: PlaceObservedV1<Value>,title: String,id: String,format: (Value)->String) -> some View {
        // The fixed decoder establishes present ⇔ non-null exactly once.
        row(title + ": " + (value.state == .present ? format(value.value!) : fieldState(value.state)),id:id)
    }
    private func coordinate(_ value: PlaceObservedV1<PlaceCoordinateV1>,title: String,id: String) -> some View {
        observed(value,title:title,id:id) { $0.raw + " · " + $0.crs }
    }
    private func endpoint(_ value: PlaceEndpointV1,title: String,id: String) -> some View {
        row(title + ": " + value.providerID + " · " + value.role.rawValue + " · " + value.coordinate.raw + " · " + value.coordinate.crs,id:id)
    }
    private func fieldState(_ value: PlaceFieldStateV1) -> String {
        switch value {
        case .present:language.text("Present", "已提供")
        case .missing:language.text("Missing", "未提供")
        case .emptyArray:language.text("Empty array · unknown", "空数组 · 未知")
        case .emptyString:language.text("Empty string · unknown", "空字符串 · 未知")
        case .null:language.text("Null · unknown", "空值 · 未知")
        case .invalid:language.text("Invalid · unavailable", "无效 · 不可用")
        case .unknown:language.text("Unknown", "未知")
        }
    }
    private func outcome(_ value: PlaceOutcomeV1) -> String {
        switch value {
        case .ok:language.text("Place information returned", "已返回地点资料")
        case .noResults:language.text("No results for this query · clarify the request", "本次查询无结果 · 可以继续澄清")
        case .rateLimited:language.text("Provider rate limited · not an empty result", "供应商限流 · 不等于无结果")
        case .providerError:language.text("Provider failure · result unavailable", "供应商失败 · 结果不可用")
        case .unknown:language.text("Result unknown · do not repeat automatically", "结果未知 · 不自动重发")
        case .invalidResponse:language.text("Invalid provider response · result unavailable", "供应商响应无效 · 结果不可用")
        case .bindingMismatch:language.text("Source binding mismatch · unavailable", "来源关联不匹配 · 不可用")
        case .stale:language.text("Expired result · verify again", "结果已过期 · 请重新核实")
        case .unsupported:language.text("Unsupported query · clarify the request", "暂不支持该查询 · 可以继续澄清")
        case .unavailable:language.text("Place information unavailable", "地点资料不可用")
        }
    }
}
