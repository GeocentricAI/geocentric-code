import SwiftUI
import AppKit

/// The white input card. `perched` lifts Geo onto its top edge, the way the
/// mascot sits on the composer in the empty state; docked composers (mid
/// conversation) leave him off so he doesn't cover the transcript.
struct ComposerCard: View {
    @ObservedObject var state: AppState
    @Binding var text: String
    var placeholder: String
    var perched: Bool = false
    var showProjectButton: Bool = false
    var showTypingCompanion: Bool = false
    /// The coding agent's composer surfaces the auto-accept toggle as a named
    /// permissions chip — the same control as the sidebar's "Auto-accept"
    /// switch, just placed where a decision about *this* codebase belongs.
    var showPermissionsChip: Bool = false

    @State private var focused = false
    @State private var textHeight: CGFloat = 20

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Geo rides along on the composer whenever he is working, and on the empty
    /// state where he is the focal point — unless he's been hidden entirely,
    /// or detached into his own floating panel (see GeoFloatingPanel), in
    /// which case he shouldn't also be sitting here.
    private var companionVisible: Bool {
        guard state.mascotVisible, !state.mascotFloating else { return false }
        if state.mascotAlwaysVisible { return true }
        return perched || state.agentActivity != .idle || (showTypingCompanion && state.busy)
    }

    private static let companionBody: CGFloat = 34

    var body: some View {
        Group {
            VStack(spacing: 0) {
                ZStack(alignment: .topLeading) {
                    if text.isEmpty {
                        Text(placeholder)
                            .font(GeoTheme.ui(14))
                            .foregroundStyle(GeoTheme.inkTertiary)
                            .padding(.horizontal, 5)
                            .padding(.top, 2)
                            .allowsHitTesting(false)
                    }
                    ComposerTextView(
                        text: $text,
                        contentHeight: $textHeight,
                        isFocused: $focused,
                        font: .systemFont(ofSize: 14),
                        grabFocusOnAppear: true,
                        onSubmit: send
                    )
                    .frame(height: min(max(textHeight, 20), 150))
                }
                .padding(.horizontal, 13)
                .padding(.top, 13)

                // Narrow panes (the Code agent pane can go down to 300pt) don't
                // fit every label at once. Rather than let SwiftUI compress a
                // Text into vertical wrapping inside a Capsule, drop to icon-only
                // chips as a deliberate, tested step before that would happen.
                ViewThatFits(in: .horizontal) {
                    composerRow(compact: false)
                    composerRow(compact: true)
                }
                .padding(.horizontal, 11)
                .padding(.bottom, 10)
                .padding(.top, 6)
            }
            .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: GeoTheme.composerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: GeoTheme.composerRadius)
                    .stroke(focused ? GeoTheme.borderStrong : GeoTheme.border, lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.045), radius: 8, y: 2)
        }
        // Geo perches on the card's own top edge, roughly above the send
        // button — not beside the card, and not covering any control, since
        // he sits above all of them with his feet on the border.
        .overlay(alignment: .topTrailing) {
            if companionVisible {
                // `state.mascotState` already distinguishes thinking (pondering)
                // from actually writing text or running a tool (active) — no need
                // to collapse that back down to one pose here.
                let mascotState = state.mascotState
                let imageHeight = GeoSpriteView.imageHeight(state: mascotState, bodyHeight: Self.companionBody)
                GeoSpriteView(state: mascotState, height: Self.companionBody)
                    .offset(x: -24, y: -(imageHeight - 5))
                    .transition(.scale(scale: 0.8, anchor: .bottom).combined(with: .opacity))
                    .allowsHitTesting(false)
            }
        }
        .animation(.linear(duration: 0.2), value: state.agentActivity)
        .animation(.linear(duration: 0.2), value: state.mascotState)
    }

    /// `compact` drops every label to an icon so the row degrades to
    /// something narrower rather than letting any single Text wrap.
    private func composerRow(compact: Bool) -> some View {
        HStack(spacing: compact ? 5 : 8) {
            Menu {
                Button("Attach a file…") { attachFile() }
                Button("Open a different project…") { chooseProject() }
                Divider()
                Button("Plan first (read-only)") { state.sendMessage("/plan") }
                Button("Review uncommitted changes") { state.sendMessage("/review") }
                Button("Run the tests") { state.sendMessage("/test") }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(GeoTheme.inkSecondary)
                    .frame(width: 26, height: 26)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()

            if showPermissionsChip {
                PermissionsChip(enabled: state.yolo, compact: compact) { state.setYolo(!state.yolo) }
            }

            if showProjectButton {
                Button(action: chooseProject) {
                    HStack(spacing: 5) {
                        Image(systemName: "folder").font(.system(size: 10))
                        if !compact {
                            Text(URL(fileURLWithPath: state.projectRoot).lastPathComponent)
                                .font(GeoTheme.ui(11.5, .medium))
                                .lineLimit(1)
                                .fixedSize()
                        }
                    }
                    .foregroundStyle(GeoTheme.ink)
                    .padding(.horizontal, compact ? 6 : 10).padding(.vertical, 5)
                    .background(GeoTheme.canvasWarm, in: Capsule())
                    .overlay(Capsule().stroke(GeoTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .fixedSize()
            }

            Spacer(minLength: 4)

            Menu {
                if state.availableModels.isEmpty {
                    Text("No models found")
                }
                ForEach(state.availableModels) { m in
                    Button {
                        state.setModel(m.name)
                    } label: {
                        Text(m.name + (m.supportsTools ? "" : "  (no tool support)"))
                    }
                }
            } label: {
                QuietMenuLabel(text: compact ? "" : (state.currentModel.isEmpty ? "model" : state.currentModel),
                              icon: compact ? "cpu" : nil)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .onAppear { state.refreshModels() }

            if showPermissionsChip && !compact {
                Menu {
                    ForEach(["low", "medium", "high", "xhigh", "max", "ultracode"], id: \.self) { level in
                        Button(level.capitalized) { state.setEffort(level) }
                    }
                } label: {
                    QuietMenuLabel(text: state.effort)
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
            }

            Button(action: state.busy ? state.interrupt : send) {
                Image(systemName: state.busy ? "stop.fill" : "arrow.up")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 27, height: 27)
                    .background(
                        Circle().fill(
                            state.busy ? GeoTheme.danger
                                       : (canSend ? GeoTheme.accent : GeoTheme.accentSoft)
                        )
                    )
            }
            .buttonStyle(.plain)
            .disabled(!canSend && !state.busy)
        }
    }

    private func send() {
        guard canSend else { return }
        state.sendMessage(text)
        text = ""
        textHeight = 20
    }

    private func attachFile() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            text += (text.isEmpty ? "" : " ") + "@\(url.path)"
        }
    }

    private func chooseProject() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Open"
        if panel.runModal() == .OK, let url = panel.url {
            state.reconnectToNewProject(url.path)
        }
    }
}
