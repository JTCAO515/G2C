import SwiftUI
import CJAPI

public enum FeasibilityLanguage: Sendable {
    case chinese, english
    func text(_ zh: String, _ en: String) -> String { self == .chinese ? zh : en }
}

/// Embed in an existing selected NEEDS flow. No new navigation, task-on-appear or auto-read.
@MainActor public struct FeasibilityView: View {
    private let model: FeasibilityModel
    private let binding: FeasibilityBinding?
    private let language: FeasibilityLanguage
    public init(model: FeasibilityModel, binding: FeasibilityBinding?, language: FeasibilityLanguage) {
        self.model = model; self.binding = binding; self.language = language
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("当前需求评估", "Current needs evaluation")).font(.headline)
            Text(language.text("整体待核实；局部检查不证明现实可行，也不授权保存或修改。",
                               "Overall unverified. Local checks do not prove real-world feasibility or authorize changes."))
            switch model.state {
            case .unavailable: Text(language.text("评估尚不可用。", "Evaluation is unavailable."))
            case .loading: ProgressView(language.text("正在读取…", "Reading…"))
            case .cancelled: Text(language.text("已停止读取。", "Read cancelled."))
            case .failed(let failure):
                Text(language.text("读取失败，结果待核实。", "Read failed; result remains unverified."))
                if case .rejected(let status, let code) = failure { Text("\(status) · \(code)").font(.caption) }
            case .loaded(let observation): report(observation.report)
            }
            Button(language.text("评估当前需求", "Evaluate current needs")) {
                guard let binding else { return }
                do {
                    let work = try model.prepare(binding)
                    Task { await model.read(work) }
                } catch { /* prepare leaves explicit unavailable state; no network attempt */ }
            }
            .disabled(binding == nil)
            .accessibilityIdentifier("feasibility.evaluate")
        }
        .textSelection(.enabled)
    }
    private func report(_ report: Components.Schemas.FeasibilityCurrentReport) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(report.status == .CONFLICT ? language.text("存在冲突", "Conflict observed") : language.text("待核实", "Unknown"))
                .font(.headline)
            Text("\(report.needs_id) · \(language.text("版本", "Revision")) \(report.revision)")
            Text("\(report.version.rawValue)\n\(report.evaluator_version.rawValue)\nSHA256 \(report.content_sha256)").font(.caption)
            ForEach(report.checks.indices, id: \.self) { index in
                let check = report.checks[index]
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(check.code) · \(check.status.rawValue)").font(.subheadline)
                    Text(language == .chinese ? check.zh : check.en)
                    ForEach(check.missing.indices, id: \.self) { i in
                        Text(language.text("待核实：", "Unverified: ") + check.missing[i])
                    }
                    ForEach(check.details.indices, id: \.self) { i in
                        Text(check.details[i].joined(separator: " · ")).font(.caption)
                    }
                }
            }
            DisclosureGroup(language.text("原始来源版本与哈希", "Original source revisions and hashes")) {
                ForEach(report.sources.indices, id: \.self) { index in
                    let source = report.sources[index]
                    Text("\(source.revision) · \(source.action_id)\nSHA256 \(source.original_input_sha256)").font(.caption)
                }
            }
        }
    }
}
