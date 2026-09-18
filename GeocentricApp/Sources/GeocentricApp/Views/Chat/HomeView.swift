import SwiftUI

/// The empty state: a serif greeting, the composer with Geo perched on it, and
/// a row of starting points. Shown until the conversation has its first message.
struct HomeView: View {
    @ObservedObject var state: AppState
    @Binding var draft: String
    let surface: WorkspaceMode

    // Picked once when this empty state appears, not re-rolled on every body
    // re-evaluation — @State's inline initial value only runs once per the
    // view's identity, which is exactly the "once per visit" cadence wanted.
    @State private var variant = Int.random(in: 0..<4)

    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 40)

            HStack(spacing: 12) {
                GeoLogo(size: 52)
                Text(greeting)
                    .font(GeoTheme.serif(33))
                    .foregroundStyle(GeoTheme.ink)
            }
            .padding(.bottom, 58)

            ComposerCard(
                state: state,
                text: $draft,
                placeholder: placeholder,
                perched: true,
                showProjectButton: surface == .code,
                showPermissionsChip: surface == .code
            )
            .frame(maxWidth: GeoTheme.composerMaxWidth)

            if surface == .code {
                HStack(alignment: .top, spacing: 10) {
                    SuggestionCard(segments: [("Create or update my ", false), ("GEOCENTRIC.md", true), (" file", false)]) {
                        state.sendMessage("/init")
                    }
                    SuggestionCard(segments: [("Search for a ", false), ("TODO", true), (" comment and fix it", false)]) {
                        state.sendMessage("Search the codebase for a small TODO comment and implement it.")
                    }
                    SuggestionCard(segments: [("Recommend areas to improve our ", false), ("tests", true)]) {
                        state.sendMessage("Review this project's test coverage and recommend the highest-value gaps to fill.")
                    }
                }
                .frame(maxWidth: GeoTheme.composerMaxWidth)
                .padding(.top, 16)
            } else if surface == .chat {
                HStack(spacing: 8) {
                    SuggestionChip(icon: "lightbulb", title: "Brainstorm") { draft = "Help me brainstorm " }
                    SuggestionChip(icon: "text.quote", title: "Rewrite") { draft = "Help me rewrite this: " }
                    SuggestionChip(icon: "questionmark.circle", title: "Learn") { draft = "Teach me about " }
                    SuggestionChip(icon: "bubble.left.and.text.bubble.right", title: "Talk it out") { draft = "I want to think through " }
                }
                .padding(.top, 18)
            }

            Spacer(minLength: 60)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 32)
    }

    private var placeholder: String {
        switch surface {
        case .chat: return "Talk with Geo — no files or code touched here"
        case .code: return "Find a small todo in the codebase and do it"
        case .work: return "What would you like to make or organize?"
        }
    }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: Date())
        // Chat has no project scope (it's the one surface that never touches
        // files — see its own placeholder above), so naming one there is just
        // wrong, not merely unnecessary.
        let suffix = surface == .chat ? "" : " — \(URL(fileURLWithPath: state.projectRoot).lastPathComponent)"
        let phrases: [String]
        switch hour {
        case 5..<12: phrases = ["Good morning", "Rise and shine", "Morning"]
        case 12..<17: phrases = ["Good afternoon", "Hey there", "Welcome back"]
        case 17..<22: phrases = ["Good evening", "Evening", "Welcome back"]
        default: phrases = ["Burning the midnight oil?", "Up late?", "Still going?"]
        }
        let phrase = phrases[variant % phrases.count]
        // The late-night phrases are already a question on their own; a
        // trailing project name reads better without another suffix stacked on.
        return hour < 5 || hour >= 22 ? phrase : "\(phrase)\(suffix)"
    }
}
