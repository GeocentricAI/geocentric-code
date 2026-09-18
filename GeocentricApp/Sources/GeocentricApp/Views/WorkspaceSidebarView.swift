import SwiftUI
import AppKit

struct WorkspaceSidebarView: View {
    @ObservedObject var state: AppState
    @Binding var workModule: WorkModule
    @State private var workExpanded = true
    @State private var sessionsExpanded = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    sidebarLabel("SPACES")
                    ForEach(WorkspaceMode.allCases) { mode in
                        workspaceRow(mode)
                    }

                    Divider().overlay(GeoTheme.border).padding(.vertical, 10)

                    sidebarLabel("PROJECT")
                    Button(action: chooseProject) {
                        Label(URL(fileURLWithPath: state.projectRoot).lastPathComponent, systemImage: "folder")
                            .font(GeoTheme.ui(12, .medium))
                            .foregroundStyle(GeoTheme.ink)
                            .lineLimit(1)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 10).padding(.vertical, 7)
                    }
                    .buttonStyle(SidebarRowButton())
                    .help(state.projectRoot)

                    if state.workspaceMode == .work {
                        Divider().overlay(GeoTheme.border).padding(.vertical, 10)
                        HStack {
                            sidebarLabel("WORK TOOLS")
                            Spacer()
                            Button { withAnimation(.easeInOut(duration: 0.18)) { workExpanded.toggle() } } label: {
                                Image(systemName: workExpanded ? "chevron.down" : "chevron.right")
                                    .font(.system(size: 9, weight: .semibold))
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(GeoTheme.inkTertiary)
                        }
                        if workExpanded {
                            ForEach(workToolGroups, id: \.title) { group in
                                Text(group.title.uppercased())
                                    .font(GeoTheme.ui(9, .bold))
                                    .foregroundStyle(GeoTheme.inkTertiary)
                                    .padding(.leading, 10).padding(.top, 7).padding(.bottom, 2)
                                ForEach(group.modules) { module in
                                    Button { workModule = module } label: {
                                        Label(module.title, systemImage: module.icon)
                                            .font(GeoTheme.ui(11.5, workModule == module ? .semibold : .regular))
                                            .foregroundStyle(workModule == module ? GeoTheme.ink : GeoTheme.inkSecondary)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                            .padding(.horizontal, 10).padding(.vertical, 5)
                                    }
                                    .buttonStyle(SidebarRowButton(selected: workModule == module))
                                }
                            }
                        }
                    }

                    Divider().overlay(GeoTheme.border).padding(.vertical, 10)
                    Button {
                        withAnimation(.easeInOut(duration: 0.18)) { sessionsExpanded.toggle() }
                        if sessionsExpanded { state.refreshSessions() }
                    } label: {
                        HStack {
                            Label("Recent sessions", systemImage: "clock.arrow.circlepath")
                            Spacer()
                            Image(systemName: sessionsExpanded ? "chevron.down" : "chevron.right")
                                .font(.system(size: 9, weight: .semibold))
                        }
                        .font(GeoTheme.ui(11.5, .medium))
                        .foregroundStyle(GeoTheme.inkSecondary)
                        .padding(.horizontal, 10).padding(.vertical, 7)
                    }
                    .buttonStyle(SidebarRowButton())

                    if sessionsExpanded {
                        ForEach(state.sessions.prefix(6)) { session in
                            Button { state.resumeSession(session.id) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(session.title.isEmpty ? "Untitled session" : session.title)
                                        .font(GeoTheme.ui(11.5))
                                        .foregroundStyle(GeoTheme.ink)
                                        .lineLimit(1)
                                    Text("\(session.age) · \(session.turns) turns")
                                        .font(GeoTheme.ui(9.5))
                                        .foregroundStyle(GeoTheme.inkTertiary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 10).padding(.vertical, 6)
                            }
                            .buttonStyle(SidebarRowButton())
                        }
                    }
                }
                .padding(12)
            }

            Divider().overlay(GeoTheme.border)
        }
        .frame(minWidth: 212, idealWidth: 232, maxWidth: 272)
        .frame(maxHeight: .infinity)
        .background(.regularMaterial)
        .onAppear { state.refreshSessions() }
    }

    private func workspaceRow(_ mode: WorkspaceMode) -> some View {
        Button { state.setWorkspaceMode(mode) } label: {
            HStack(spacing: 9) {
                Image(systemName: mode.systemImage).frame(width: 14)
                VStack(alignment: .leading, spacing: 1) {
                    Text(mode.title).font(GeoTheme.ui(12, state.workspaceMode == mode ? .semibold : .regular))
                    Text(mode.subtitle).font(GeoTheme.ui(9.5)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Spacer(minLength: 0)
            }
            .foregroundStyle(state.workspaceMode == mode ? GeoTheme.ink : GeoTheme.inkSecondary)
            .padding(.horizontal, 10).padding(.vertical, 7)
        }
        .buttonStyle(SidebarRowButton(selected: state.workspaceMode == mode))
    }

    private func sidebarLabel(_ title: String) -> some View {
        Text(title).font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
            .padding(.horizontal, 10).padding(.bottom, 3)
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

private struct SidebarRowButton: ButtonStyle {
    var selected = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                (selected ? GeoTheme.accentWash : (configuration.isPressed ? GeoTheme.border.opacity(0.55) : .clear)),
                in: RoundedRectangle(cornerRadius: 7)
            )
    }
}

private struct WorkToolGroup {
    let title: String
    let modules: [WorkModule]
}

private let workToolGroups: [WorkToolGroup] = [
    .init(title: "Create", modules: [.documents, .markdown, .sheets, .presentations, .whiteboard]),
    .init(title: "Organize", modules: [.notes, .tasks, .calendar, .board, .knowledge]),
    .init(title: "Explore", modules: [.files, .pdf, .csv, .images, .diagrams, .database]),
]
