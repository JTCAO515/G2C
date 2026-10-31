import SwiftUI

/// Synthetic source data only. No link is opened, query repeated, source clock
/// refreshed or Trip/Memory mutated by displaying these original RUN frames.
public struct FactToolTranscriptView: View {
    let transcript: FactToolTranscriptV1
    let language: TripLanguage
    public init(transcript: FactToolTranscriptV1,language: TripLanguage) { self.transcript = transcript;self.language = language }
    public var body: some View {
        VStack(alignment:.leading,spacing:14) {
            row(language.text("Synthetic local evidence · NOT live weather or eligibility", "本地合成证据 · 非真实天气或资格结论"),"fact.origin")
            if transcript.outputs.isEmpty { row(language.text("No complete fact result received", "尚未收到完整事实资料"),"fact.pending") }
            ForEach(transcript.outputs.indices,id:\.self) { i in result(transcript.outputs[i].result,index:i) }
            if let answer = transcript.answer {
                row(language.text("Machine explanation · not an official translation", "机器说明 · 非官方翻译"),"fact.machine.label")
                row(language == .english ? answer.english : answer.chinese,"fact.answer")
            }
            if transcript.hasPendingFrame { row(language.text("Incomplete frame · not a completed result", "结果片段尚不完整 · 不作为完整结果展示"),"fact.pendingFrame") }
            row(language.text("Original evaluation only. Reading it again does not refresh validity, authorize a query or confirm a trip.", "仅为原评估时刻的结果；再次读取不刷新有效期、不授权新查询，也不确认行程。"),"fact.noConfirmation")
        }.frame(maxWidth:.infinity,alignment:.leading)
    }
    private func row(_ text: String,_ id: String) -> some View {
        TripVerificationText(text:text,style:.body).frame(maxWidth:.infinity,alignment:.leading).accessibilityIdentifier(id)
    }
    private func field(_ title: String,_ value: String,_ id: String) -> some View {
        VStack(alignment:.leading,spacing:4) {
            TripVerificationText(text:title,style:.caption).frame(maxWidth:.infinity,alignment:.leading).accessibilityIdentifier(id + ".label")
            row(value,id)
        }
    }
    private func result(_ value: FactResultV1,index: Int) -> some View {
        let p = "fact.output.\(index)"
        return VStack(alignment:.leading,spacing:10) {
            row(outcome(value.outcome),p + ".outcome")
            row(status(value.status),p + ".status")
            row(value.query.factKey + " · " + value.query.region + " · " + value.query.dates.start + " — " + value.query.dates.end,p + ".query")
            field(language.text("Explicit query conditions", "明确查询条件"),conditions(value.query.conditions),p + ".conditions")
            field(language.text("Evaluated at", "评估时点"),stamp(value.evaluatedAt),p + ".evaluated")
            if let original = value.originalValue { row(original,p + ".value") }
            else { row(language.text("No supported value selected", "未选定适用的事实值"),p + ".value") }
            row(language.text("Applicability explanation · not source truth or official translation", "适用性说明 · 不代表来源真实或官方翻译"),p + ".summary.label")
            row(language == .english ? value.english : value.chinese,p + ".summary")
            if value.sources.isEmpty { row(language.text("No source body returned", "未返回来源正文"),p + ".noSource") }
            ForEach(value.sources.indices,id:\.self) { i in source(value.sources[i],prefix:p + ".source.\(i)") }
        }
    }
    private func source(_ value: FactSourceV1,prefix p: String) -> some View {
        VStack(alignment:.leading,spacing:8) {
            field(language.text("Synthetic source", "合成来源"),value.sourceURL,p + ".url")
            row(value.originalValue,p + ".original")
            row(status(value.status) + (value.reasons.isEmpty ? "" : " · " + value.reasons.joined(separator:", ")),p + ".status")
            field(language.text("Retrieved at", "检索时点"),stamp(value.retrievedAt),p + ".retrieved")
            if let time = value.declarations.publishedAt { field(language.text("Published at", "发布时点"),stamp(time),p + ".published") }
            else { row(language.text("Publication time: not declared", "发布时间：未声明"),p + ".published") }
            if let time = value.declarations.expiresAt { field(language.text("Declared expiry", "声明失效时点"),stamp(time),p + ".expiry") }
            else { row(language.text("Expiry: not declared · unknown", "失效时点：未声明 · 未知"),p + ".expiry") }
            if let regions = value.declarations.regions { field(language.text("Declared regions", "声明地域"),regions.joined(separator:" · "),p + ".regions") }
            else { row(language.text("Region: not declared", "适用地域：未声明"),p + ".regions") }
            if let dates = value.declarations.dates { field(language.text("Inclusive dates", "适用日期（含起止日）"),dates.start + " — " + dates.end,p + ".dates") }
            else { row(language.text("Date window: not declared", "适用日期：未声明"),p + ".dates") }
            if let declared = value.declarations.conditions { field(language.text("Declared conditions", "声明条件"),conditions(declared),p + ".conditions") }
            else { row(language.text("Conditions: not declared", "适用条件：未声明"),p + ".conditions") }
        }.padding(.vertical,8)
    }
    private func conditions(_ value: [String:String]) -> String {
        value.isEmpty ? language.text("none supplied", "未提供") : value.keys.sorted().map { $0 + "=" + value[$0]! }.joined(separator:"\n")
    }
    private func stamp(_ value: PlaceTimestampV1) -> String { value.iso8601 + " · fold=" + String(value.fold) }
    private func status(_ value: FactStatusV1) -> String {
        switch value {
        case .supported:language.text("Declared applicability supported · not verified truth", "声明覆盖查询 · 非真实性查证")
        case .outOfRange:language.text("Outside declared scope", "超出声明适用范围")
        case .expired:language.text("Expired at original evaluation · verify again", "原评估时已过期 · 需核实")
        case .conflicting:language.text("Conflicting sources · no answer selected", "来源冲突 · 不能选定答案")
        case .unknown:language.text("Applicability unknown · verification needed", "适用性未知 · 待核实")
        }
    }
    private func outcome(_ value: FactOutcomeV1) -> String {
        switch value {
        case .ok:language.text("Synthetic evidence returned", "已返回合成证据")
        case .noResults:language.text("No applicable source · not a precise answer", "无适用来源 · 不能补充精确答案")
        case .rateLimited:language.text("Synthetic source rate limited", "合成来源限流")
        case .invalidResponse:language.text("Invalid source response · unavailable", "来源响应无效 · 不可用")
        case .sourceFailure:language.text("Source failure · result unavailable", "来源失败 · 结果不可用")
        }
    }
}
