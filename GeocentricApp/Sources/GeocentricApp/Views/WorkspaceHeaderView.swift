import SwiftUI

/// Deliberately quiet window chrome. The switcher is the only thing with real
/// presence; everything else is dimmed until hovered, so the canvas — greeting,
/// composer, Geo — carries the screen. Utilities live behind one overflow menu
/// rather than a row of competing icons.
struct WorkspaceHeaderView: View {
    @ObservedObject var state: AppState
    @Binding var focusMode: Bool
    @Binding var commandPaletteVisible: Bool
    @Binding var mcpManagerVisible: Bool

    var body: some View {
        ZStack {
            SurfaceSwitcher(selection: Binding(
                get: { state.workspaceMode },
                set: { state.setWorkspaceMode($0) }
            ))

            HStack(spacing: 6) {
                Spacer()

                // The approval banner itself (see ApprovalBannerView, now shown
                // in both Chat and Code) is the actionable surface for this —
                // a second, non-interactive "Needs your approval" pill up here
                // was just a duplicate that did nothing when you clicked it.
                if state.agentActivity != .idle && state.agentActivity != .waitingForApproval {
                    ActivityPill(activity: state.agentActivity)
                        .transition(.opacity.combined(with: .scale(scale: 0.9)))
                }

                QuietChromeButton(icon: "command", help: "Command palette (⌘K)") {
                    commandPaletteVisible = true
                }

                Menu {
                    Button("MCP servers…") { mcpManagerVisible = true }
                    Divider()
                    Button(focusMode ? "Leave focus mode" : "Focus mode") {
                        withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) { focusMode.toggle() }
                    }
                    Divider()
                    Button("New session") { state.newSession() }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 26, height: 26)
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
                .foregroundStyle(GeoTheme.inkTertiary)
            }
            .padding(.leading, 26) // the rail covers most of the traffic-light inset now
            .padding(.trailing, 14)
        }
        .frame(height: 46)
        .background(GeoTheme.canvas)
        .animation(.easeInOut(duration: 0.2), value: state.agentActivity)
    }
}

/// Low-contrast until hovered, so chrome never competes with content.
private struct QuietChromeButton: View {
    let icon: String
    let help: String
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12.5, weight: .medium))
                .foregroundStyle(hovering ? GeoTheme.ink : GeoTheme.inkTertiary)
                .frame(width: 26, height: 26)
                .background(
                    RoundedRectangle(cornerRadius: 7)
                        .fill(hovering ? GeoTheme.borderStrong.opacity(0.28) : .clear)
                )
        }
        .buttonStyle(.plain)
        .help(help)
        .onHover { hovering = $0 }
    }
}

private struct ActivityPill: View {
    let activity: AgentActivity
    @State private var pulse = false

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(GeoTheme.accent)
                .frame(width: 5, height: 5)
                .scaleEffect(pulse ? 1.35 : 0.85)
                .animation(.easeInOut(duration: 0.75).repeatForever(autoreverses: true), value: pulse)
            Text(activity.label)
                .font(GeoTheme.ui(10.5, .medium))
                .lineLimit(1)
        }
        .foregroundStyle(GeoTheme.inkSecondary)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(GeoTheme.canvasWarm, in: Capsule())
        .overlay(Capsule().stroke(GeoTheme.border, lineWidth: 1))
        .onAppear { pulse = true }
    }
}
