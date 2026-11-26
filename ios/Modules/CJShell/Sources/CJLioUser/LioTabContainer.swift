#if os(iOS)
import SwiftUI

/// The tab bar (#1724): Chat, Trips, Tools (when the build shows it) and Me. It owns nothing but the tabs; the
/// chat, the trip pages and the tool pages are passed in, and `router` says which tab is selected. The router is
/// put in the environment, so any page can open a tool with `LioRouter.open(_:)`.
struct LioTabContainer<Chat: View, Trips: View, Tools: View, Me: View>: View {
    let language: LioLanguage
    @Bindable var router: LioRouter
    let chat: Chat
    let trips: Trips
    let tools: Tools?
    let me: Me

    init(language: LioLanguage, router: LioRouter,
         @ViewBuilder chat: () -> Chat, @ViewBuilder trips: () -> Trips,
         @ViewBuilder tools: () -> Tools, @ViewBuilder me: () -> Me) {
        self.language = language
        self.router = router
        self.chat = chat()
        self.trips = trips()
        self.tools = router.toolsShown ? tools() : nil
        self.me = me()
    }

    var body: some View {
        TabView(selection: $router.tab) {
            chat
                .background(LioTabBarAppearance().frame(width: 0, height: 0))
                .tabItem { Label(language.text("Chat", "聊天"), systemImage: "bubble.left") }
                .tag(LioTab.chat)
            trips
                .background(LioTabBarAppearance().frame(width: 0, height: 0))
                .tabItem { Label(language.text("Trips", "行程"), systemImage: "suitcase") }
                .tag(LioTab.trips)
            if let tools {
                tools
                    .background(LioTabBarAppearance().frame(width: 0, height: 0))
                    .tabItem { Label(LioToolCatalog.title(language), systemImage: "square.grid.2x2") }
                    .tag(LioTab.tools)
            }
            // #1452: Memory moves into Me, together with the settings and account rows from the chat menu.
            me
                .background(LioTabBarAppearance().frame(width: 0, height: 0))
                .tabItem { Label(language.text("Me", "我的"), systemImage: "person.crop.circle") }
                .tag(LioTab.me)
        }
        .environment(router)
    }
}
#endif
