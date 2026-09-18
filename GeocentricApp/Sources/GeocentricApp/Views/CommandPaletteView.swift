import SwiftUI

struct CommandPaletteView: View {
    @ObservedObject var state: AppState
    @Binding var isPresented: Bool
    @Binding var workModule: WorkModule
    @State private var query = ""
    @FocusState private var searchFocused: Bool

    // Cowork is hidden from navigation for now (see WorkspaceMode.visibleCases),
    // so its palette entries are withheld too rather than opening a surface
    // there's no other way to reach.
    private var actions: [PaletteAction] {
        [
            .init("Open Chat", "Conversation without tools", "bubble.left.and.bubble.right") { state.setWorkspaceMode(.chat) },
            .init("Open Code", "Local coding workspace", "chevron.left.forwardslash.chevron.right") { state.setWorkspaceMode(.code) },
            .init("New conversation", "Start fresh with Geo", "square.and.pencil") { state.newSession() },
            .init("Review current changes", "Ask Geo for a code review", "checkmark.seal") { state.setWorkspaceMode(.code); state.sendMessage("/review") },
            .init("Run project tests", "Ask Geo to find and run tests", "testtube.2") { state.setWorkspaceMode(.code); state.sendMessage("/test") },
        ]
    }

    private var filtered: [PaletteAction] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return actions }
        return actions.filter { $0.title.lowercased().contains(needle) || $0.subtitle.lowercased().contains(needle) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 9) {
                Image(systemName: "magnifyingglass").foregroundStyle(GeoTheme.inkTertiary)
                TextField("Type a command or search tools", text: $query)
                    .textFieldStyle(.plain)
                    .font(GeoTheme.ui(14))
                    .focused($searchFocused)
                Text("esc")
                    .font(GeoTheme.mono(10))
                    .foregroundStyle(GeoTheme.inkTertiary)
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 4))
            }
            .padding(14)
            .background(GeoTheme.card)

            Divider().overlay(GeoTheme.border)

            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(filtered) { action in
                        Button {
                            action.run()
                            isPresented = false
                        } label: {
                            HStack(spacing: 11) {
                                Image(systemName: action.icon)
                                    .frame(width: 17)
                                    .foregroundStyle(GeoTheme.accent)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(action.title).font(GeoTheme.ui(12.5, .medium)).foregroundStyle(GeoTheme.ink)
                                    Text(action.subtitle).font(GeoTheme.ui(10.5)).foregroundStyle(GeoTheme.inkTertiary)
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 14).padding(.vertical, 9)
                        }
                        .buttonStyle(PaletteActionStyle())
                    }
                }
                .padding(6)
            }
            .frame(maxHeight: 360)

            Divider().overlay(GeoTheme.border)
            HStack {
                Text("⌘K to open · ↑↓ to navigate · ↵ to run")
                    .font(GeoTheme.ui(10.5)).foregroundStyle(GeoTheme.inkTertiary)
                Spacer()
                Text("Local only")
                    .font(GeoTheme.ui(10.5, .medium)).foregroundStyle(GeoTheme.success)
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
        }
        .frame(width: 520)
        .background(GeoTheme.card)
        .onAppear { searchFocused = true }
    }
}

private struct PaletteAction: Identifiable {
    let id = UUID()
    let title: String
    let subtitle: String
    let icon: String
    let run: () -> Void

    init(_ title: String, _ subtitle: String, _ icon: String, run: @escaping () -> Void) {
        self.title = title
        self.subtitle = subtitle
        self.icon = icon
        self.run = run
    }
}

private struct PaletteActionStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(configuration.isPressed ? GeoTheme.accentWash : Color.clear,
                        in: RoundedRectangle(cornerRadius: 8))
    }
}
