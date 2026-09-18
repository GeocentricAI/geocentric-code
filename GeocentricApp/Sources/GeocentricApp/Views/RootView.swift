import SwiftUI

/// The stable desktop frame for all three Geocentric workspaces. Views change
/// inside this shell; the window chrome and primary navigation do not, which
/// keeps mode switches calm and preserves keyboard/multi-window affordances.
struct RootView: View {
    @StateObject private var state = AppState()
    @StateObject private var workStore = LocalWorkspaceStore()
    @SceneStorage("geocentric.focusMode") private var focusMode = false
    @SceneStorage("geocentric.workModule") private var storedWorkModule = WorkModule.documents.rawValue
    @State private var railPanel: RailPanel?
    @State private var commandPaletteVisible = false
    @State private var mcpManagerVisible = false
    @State private var chatDraft = ""
    @State private var codeDraft = ""
    @State private var workDraft = ""

    private var workModule: Binding<WorkModule> {
        Binding(
            get: { WorkModule(rawValue: storedWorkModule) ?? .documents },
            set: { storedWorkModule = $0.rawValue }
        )
    }

    var body: some View {
        // The rail runs the full height of the window and the header sits only
        // over the content column. Banding the header across the whole width
        // read as a title bar; this way the chrome disappears into the canvas.
        HStack(spacing: 0) {
            if !focusMode {
                IconRailView(state: state, panel: $railPanel)

                // The rail icons are the only control for this drawer now —
                // a separate header toggle used to gate the same panel and
                // the two fought each other (click a rail icon, nothing
                // happened unless the other control had already been
                // flipped on once).
                if let panel = railPanel {
                    RailDrawerView(state: state, panel: panel)
                        .transition(.move(edge: .leading).combined(with: .opacity))
                } else if state.workspaceMode == .work {
                    WorkspaceSidebarView(state: state, workModule: workModule)
                        .transition(.move(edge: .leading).combined(with: .opacity))
                    Divider().overlay(GeoTheme.border)
                }
            }

            VStack(spacing: 0) {
                WorkspaceHeaderView(
                    state: state,
                    focusMode: $focusMode,
                    commandPaletteVisible: $commandPaletteVisible,
                    mcpManagerVisible: $mcpManagerVisible
                )

                ZStack {
                    GeoTheme.canvas
                    workspaceContent
                        .transition(.opacity.combined(with: .scale(scale: 0.99)))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(GeoTheme.canvas)
        .animation(.spring(response: 0.32, dampingFraction: 0.86), value: railPanel)
        .animation(.easeInOut(duration: 0.2), value: state.workspaceMode)
        .overlay { connectionOverlay }
        .sheet(isPresented: $commandPaletteVisible) {
            CommandPaletteView(state: state, isPresented: $commandPaletteVisible, workModule: workModule)
        }
        .sheet(isPresented: $mcpManagerVisible) {
            MCPServerManagerView(isPresented: $mcpManagerVisible)
        }
        .onAppear {
            if state.connection == .disconnected { state.connect() }
            // A prior launch could have persisted .work via @Published/SceneStorage
            // before it was hidden; land somewhere reachable instead.
            if !WorkspaceMode.visibleCases.contains(state.workspaceMode) {
                state.setWorkspaceMode(.chat)
            }
        }
        .onChange(of: focusMode) { _, focused in
            if focused { railPanel = nil }
        }
    }

    @ViewBuilder
    private var workspaceContent: some View {
        switch state.workspaceMode {
        case .chat:
            ChatView(state: state, draft: $chatDraft, surface: .chat)
        case .code:
            CodeWorkspaceView(state: state, draft: $codeDraft, focusMode: $focusMode)
        case .work:
            WorkSurfaceView(state: state, store: workStore, module: workModule, draft: $workDraft, focusMode: $focusMode)
        }
    }

    @ViewBuilder
    private var connectionOverlay: some View {
        switch state.connection {
        case .ready:
            EmptyView()
        case .disconnected, .connecting:
            overlayCard {
                VStack(spacing: 12) {
                    GeoSpriteView(state: .active, height: 42)
                    Text("Waking Geo up…").font(GeoTheme.ui(13)).foregroundStyle(GeoTheme.inkSecondary)
                }
            }
        case .ollamaUnreachable(let host):
            overlayCard {
                errorBody(
                    title: "Can't reach Ollama",
                    message: "No response from \(host). Start it with `ollama serve`, then retry."
                )
            }
        case .fatal(let message):
            overlayCard { errorBody(title: "Couldn't start Geocentric", message: message) }
        }
    }

    private func overlayCard<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        ZStack {
            GeoTheme.canvas.opacity(0.92)
            content()
                .padding(28)
                .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(GeoTheme.border, lineWidth: 1))
                .shadow(color: .black.opacity(0.08), radius: 18, y: 5)
        }
    }

    private func errorBody(title: String, message: String) -> some View {
        VStack(spacing: 9) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 24)).foregroundStyle(GeoTheme.warn)
            Text(title).font(GeoTheme.serif(17)).foregroundStyle(GeoTheme.ink)
            Text(message)
                .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkSecondary)
                .multilineTextAlignment(.center).frame(maxWidth: 330)
            Button("Retry") { state.connect() }
                .font(GeoTheme.ui(12, .medium))
                .padding(.horizontal, 16).padding(.vertical, 7)
                .background(GeoTheme.accent, in: Capsule())
                .foregroundStyle(.white)
                .buttonStyle(.plain)
                .padding(.top, 4)
        }
    }
}
