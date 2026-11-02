#if os(iOS)
import SwiftUI
import CJRunClient

struct TypedMemoryCollectionView: View {
    let host: TypedMemoryContainerHost
    @Bindable var shell: ShellState
    @Environment(\.dismiss) private var dismiss
    @State private var index = 0
    private var language: ShellLanguage { shell.language }
    var body: some View {
        let questions = host.collectionQuestions
        Group {
            if questions.indices.contains(index) {
                let question = questions[index]
                TypedMemoryManual(host:host,language:language,allowedOptionIDs:question.optionIDs,
                    questionControls:.init(progress:language.text("Question ","问题 ")+String(index+1)+"/"+String(questions.count),prompt:prompt(question.kind),next:{
                        if index+1 < questions.count { index += 1 } else { dismiss() }
                    },skip:{ dismiss();shell.selectedTab = .assistant })).id(question.id)
            } else {
                RunReadableText(text:language.text("Questions are unavailable in the current account context.","当前账号上下文的问题不可用。"))
            }
        }.navigationBarTitleDisplayMode(.inline)
    }
    private func prompt(_ kind:String) -> String {
        switch kind {
        case "fact":language.text("What would you like us to know for your travels?","关于旅行，有哪些希望记住的情况？")
        case "experience":language.text("Which travel experience would you like to keep?","有哪些旅行经历希望记下来？")
        default:language.text("What travel preference would you like to save?","有哪些希望保存的旅行偏好？")
        }
    }
}
#endif
