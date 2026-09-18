import SwiftUI
import AppKit

// Code is chat-first: just Geo's transcript, full width, with a git status
// bar and the composer. No file tree, no separate editor pane — those were
// asked to go entirely. A file the agent touches shows up as a diff right in
// its tool-call row (see TranscriptToolRow), which is where you'd actually
// look for it while following along.
struct CodeWorkspaceView: View {
    @ObservedObject var state: AppState
    @Binding var draft: String
    @Binding var focusMode: Bool

    var body: some View {
        VStack(spacing: 0) {
            CodeWorkspaceToolbar(state: state, focusMode: $focusMode)
            CodeAgentPane(state: state, draft: $draft)
        }
        .background(GeoTheme.canvas)
    }
}

private struct CodeWorkspaceToolbar: View {
    @ObservedObject var state: AppState
    @Binding var focusMode: Bool

    var body: some View {
        // Labels drop to icons before anything is allowed to clip or wrap.
        ViewThatFits(in: .horizontal) {
            toolbar(showActionLabels: true, showSubtitle: true)
            toolbar(showActionLabels: true, showSubtitle: false)
            toolbar(showActionLabels: false, showSubtitle: false)
        }
        .frame(height: 42)
        .background(GeoTheme.canvasWarm)
        .overlay(alignment: .bottom) { Rectangle().fill(GeoTheme.border).frame(height: 1) }
    }

    private func toolbar(showActionLabels: Bool, showSubtitle: Bool) -> some View {
        HStack(spacing: 10) {
            // The project name is the switcher — Review/Verify/Commit already
            // live in the composer's attach menu and the git bar below, so
            // this toolbar doesn't need its own copies of them.
            Button(action: chooseProject) {
                Label(URL(fileURLWithPath: state.projectRoot).lastPathComponent,
                      systemImage: "chevron.left.forwardslash.chevron.right")
                    .font(GeoTheme.ui(12, .semibold))
                    .foregroundStyle(GeoTheme.ink)
                    .lineLimit(1)
                if showActionLabels {
                    Image(systemName: "chevron.up.chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(GeoTheme.inkTertiary)
                }
            }
            .buttonStyle(.plain)
            .layoutPriority(1)
            .help("Switch project folder")

            if showSubtitle {
                Text("Code workspace")
                    .font(GeoTheme.ui(11))
                    .foregroundStyle(GeoTheme.inkTertiary)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            Button { withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) { focusMode.toggle() } } label: {
                Image(systemName: focusMode ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
            }
            .buttonStyle(CodeToolbarButton())
            .help(focusMode ? "Leave focus mode" : "Focus editor")
        }
        .padding(.horizontal, 16)
        .frame(height: 42)
    }

    private func chooseProject() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Open"
        panel.directoryURL = URL(fileURLWithPath: state.projectRoot)
        guard panel.runModal() == .OK, let url = panel.url else { return }
        state.reconnectToNewProject(url.path)
    }
}

private struct CodeToolbarButton: ButtonStyle {
    var tint: Color = GeoTheme.inkSecondary
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(GeoTheme.ui(11.5, .medium))
            .foregroundStyle(tint)
            .padding(.horizontal, 9).padding(.vertical, 6)
            .background(configuration.isPressed ? GeoTheme.border.opacity(0.6) : GeoTheme.card,
                        in: RoundedRectangle(cornerRadius: 7))
            .overlay(RoundedRectangle(cornerRadius: 7).stroke(GeoTheme.border, lineWidth: 1))
    }
}

private struct CodeAgentPane: View {
    @ObservedObject var state: AppState
    @Binding var draft: String
    @StateObject private var git = GitStatusProbe()

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                // Geo already rides on the composer once there's a
                // conversation going (see ComposerCard's companion) — showing
                // him here too, at the same time, reads as two mascots on
                // screen at once. This header portrait is only for the empty
                // state, before that first message exists, and never comes
                // back after.
                if state.timeline.isEmpty && state.mascotVisible && !state.mascotFloating {
                    GeoSpriteView(state: state.mascotState, height: 26)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text("Geo · Code agent").font(GeoTheme.ui(12, .semibold))
                    Text(state.agentActivity.label).font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Spacer()
                Button { state.newSession() } label: { Image(systemName: "square.and.pencil") }
                    .buttonStyle(.plain).foregroundStyle(GeoTheme.inkTertiary).help("New session")
            }
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background(GeoTheme.canvasWarm)
            .overlay(alignment: .bottom) { Rectangle().fill(GeoTheme.border).frame(height: 1) }

            if state.timeline.isEmpty {
                VStack(alignment: .leading, spacing: 11) {
                    Text("Ready to work locally.")
                        .font(GeoTheme.serif(20)).foregroundStyle(GeoTheme.ink)
                    Text("Geo can inspect the project, propose a plan, apply reviewed changes, and verify the result.")
                        .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    VStack(spacing: 7) {
                        codePrompt("Find the next small improvement")
                        codePrompt("Review the current working tree")
                        codePrompt("Explain this project")
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(16)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 4) {
                            ForEach(state.timeline.suffix(40)) { entry in
                                if entry.kind == .toolCall, let record = entry.toolCall {
                                    TranscriptToolRow(record: record)
                                } else {
                                    TranscriptRow(entry: entry)
                                }
                            }
                        }
                        .padding(.horizontal, 14).padding(.vertical, 12)

                        if state.busy {
                            TurnStatsLine(state: state)
                                .padding(.horizontal, 14).padding(.bottom, 10)
                        }
                    }
                    .onChange(of: state.timeline.count) { proxy.scrollTo(state.timeline.last?.id, anchor: .bottom) }
                }
            }

            if git.isRepo {
                GitStatusBar(state: state, git: git)
            }

            // Lost when this pane was simplified down from the old file-tree
            // layout — a tool needing approval, ask_user, or a plan proposal
            // had nowhere left to render, so it silently did nothing instead
            // of the turn actually being stuck waiting on a banner nobody saw.
            if let approval = state.pendingApproval {
                ApprovalBannerView(request: approval) { state.respondToApproval($0) }
                    .padding(.horizontal, 10).padding(.top, 8)
            }
            if let question = state.pendingQuestion {
                QuestionBannerView(request: question) {
                    state.answerQuestion(option: $0, question: question)
                }
                .padding(.horizontal, 10).padding(.top, 8)
            }
            if let plan = state.activePlan {
                PlanView(
                    plan: plan,
                    onAcceptManual: { state.acceptPlan(auto: false) },
                    onAcceptAuto: { state.acceptPlan(auto: true) },
                    onRevise: { state.revisePlan(feedback: $0) },
                    onCancel: { state.cancelPlan() }
                )
                .padding(.horizontal, 10).padding(.top, 8)
            }

            ComposerCard(
                state: state,
                text: $draft,
                placeholder: "Ask Geo to work in this codebase",
                showTypingCompanion: true,
                showPermissionsChip: true
            )
            .padding(10)
        }
        .background(GeoTheme.canvasWarm)
        .onAppear { git.refresh(path: state.projectRoot) }
        .onChange(of: state.projectRoot) { _, path in git.refresh(path: path) }
        .onChange(of: state.filesChanged.count) { git.refresh(path: state.projectRoot) }
        .onChange(of: state.busy) { _, busy in if !busy { git.refresh(path: state.projectRoot) } }
    }

    private func codePrompt(_ text: String) -> some View {
        Button(text) { draft = text }
            .font(GeoTheme.ui(11.5, .medium))
            .foregroundStyle(GeoTheme.inkSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(GeoTheme.border, lineWidth: 1))
            .buttonStyle(.plain)
    }
}

/// A flowing transcript line rather than a chat bubble: plain text for
/// statements, dimmed italic for streamed prose still arriving. Matches a
/// coding agent's transcript register more than a messaging app's.
private struct TranscriptRow: View {
    @ObservedObject var entry: TimelineEntry

    var body: some View {
        switch entry.kind {
        case .userMessage:
            // Flowing transcript register, left-aligned like Geo's own
            // replies — a small muted "You" label is the only thing telling
            // the two apart, rather than a message-app bubble on the right.
            VStack(alignment: .leading, spacing: 1) {
                Text("You").font(GeoTheme.ui(10, .semibold)).foregroundStyle(GeoTheme.inkTertiary)
                Text(entry.text)
                    .font(GeoTheme.ui(12.5, .medium))
                    .foregroundStyle(GeoTheme.ink)
                    .textSelection(.enabled)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 3)
        case .assistantMessage:
            if !entry.text.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    if !entry.thinkingText.isEmpty {
                        ThoughtProcessDisclosure(text: entry.thinkingText)
                    }
                    MarkdownishText(entry.text)
                    CopyButton(text: entry.text)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 3)
            }
        case .commandOutput:
            Text(entry.text)
                .font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkSecondary)
                .textSelection(.enabled)
                .padding(.vertical, 3)
        case .note:
            HStack(spacing: 5) {
                Image(systemName: noteIcon(entry.style)).font(.system(size: 10))
                Text(entry.text).font(GeoTheme.ui(11.5))
            }
            .foregroundStyle(noteColor(entry.style))
            .padding(.vertical, 2)
        case .toolCall, .planProposal:
            EmptyView()
        }
    }

    private func noteIcon(_ style: NoteStyle) -> String {
        switch style {
        case .error: return "exclamationmark.octagon"
        case .warn: return "exclamationmark.triangle"
        case .success: return "checkmark.circle"
        case .info: return "info.circle"
        }
    }
    private func noteColor(_ style: NoteStyle) -> Color {
        switch style {
        case .error: return GeoTheme.danger
        case .warn: return GeoTheme.warn
        case .success: return GeoTheme.success
        case .info: return GeoTheme.inkTertiary
        }
    }
}

/// A collapsible "Ran a command ›" line rather than a bordered card — reads as
/// part of the transcript's flow instead of an interruption to it.
private struct TranscriptToolRow: View {
    @ObservedObject var record: ToolCallRecord
    @State private var expanded = false

    private var hasDetail: Bool { !(record.diffText ?? "").isEmpty || !record.outputText.isEmpty }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button {
                if hasDetail { withAnimation(.easeOut(duration: 0.12)) { expanded.toggle() } }
            } label: {
                HStack(spacing: 5) {
                    statusIcon
                    Text(actionLabel).font(GeoTheme.ui(12, .medium)).foregroundStyle(GeoTheme.ink)
                    if showsRawArgs, !record.argsText.isEmpty {
                        Text(record.argsText).font(GeoTheme.mono(10.5)).foregroundStyle(GeoTheme.inkTertiary).lineLimit(1)
                    }
                    if hasDetail {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(GeoTheme.inkTertiary)
                            .rotationEffect(.degrees(expanded ? 90 : 0))
                    }
                }
            }
            .buttonStyle(.plain)

            if expanded {
                if let diff = record.diffText, !diff.isEmpty {
                    DiffTextView(diff: diff)
                        .padding(8)
                        .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 7))
                } else if !record.outputText.isEmpty {
                    Text(record.outputText)
                        .font(GeoTheme.mono(10.5))
                        .foregroundStyle(record.status == .failed ? GeoTheme.danger : GeoTheme.inkSecondary)
                        .textSelection(.enabled)
                        .lineLimit(30)
                        .padding(8)
                        .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 7))
                }
            }
        }
        .padding(.vertical, 2)
    }

    /// The named cases already fold their key argument into the label itself
    /// (e.g. "Read app.py"), so the raw `path=…` text would just repeat it.
    private var showsRawArgs: Bool {
        !["run_command", "run_python", "read_file", "write_file", "edit_file",
          "multi_edit", "grep", "glob_files", "list_dir"].contains(record.name)
    }

    private var actionLabel: String {
        let hint = record.pathHint
        switch record.name {
        case "run_command", "run_python": return "Ran a command"
        case "read_file": return hint.isEmpty ? "Read a file" : "Read \(hint)"
        case "write_file", "edit_file", "multi_edit": return hint.isEmpty ? "Edited a file" : "Edited \(hint)"
        case "grep": return hint.isEmpty ? "Searched" : "Searched for \(hint)"
        case "glob_files": return "Searched files"
        case "list_dir": return "Listed files"
        default: return record.name.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    @ViewBuilder
    private var statusIcon: some View {
        switch record.status {
        case .running: ProgressView().controlSize(.small).scaleEffect(0.55).frame(width: 12)
        case .ok: Image(systemName: "checkmark").font(.system(size: 9, weight: .bold)).foregroundStyle(GeoTheme.success)
        case .failed: Image(systemName: "xmark").font(.system(size: 9, weight: .bold)).foregroundStyle(GeoTheme.danger)
        }
    }
}

/// Live elapsed time + token count while a turn is running — the same
/// "13m 55s · 24.0k tokens · thinking…" register a coding agent's transcript
/// uses to show it hasn't stalled.
private struct TurnStatsLine: View {
    @ObservedObject var state: AppState

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            HStack(spacing: 6) {
                Image(systemName: "asterisk")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(GeoTheme.accent)
                    .rotationEffect(.degrees(context.date.timeIntervalSince1970.truncatingRemainder(dividingBy: 2) < 1 ? 0 : 45))
                Text([elapsed(context.date), tokenLabel, state.thinkingHint.isEmpty ? state.agentActivity.label : state.thinkingHint]
                    .filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkTertiary)
            }
        }
    }

    private func elapsed(_ now: Date) -> String {
        guard let start = state.turnStartedAt else { return "" }
        let seconds = max(0, Int(now.timeIntervalSince(start)))
        return seconds < 60 ? "\(seconds)s" : "\(seconds / 60)m \(seconds % 60)s"
    }

    private var tokenLabel: String {
        guard state.totalTokens > 0 else { return "" }
        return state.totalTokens >= 1000
            ? String(format: "%.1fk tokens", Double(state.totalTokens) / 1000)
            : "\(state.totalTokens) tokens"
    }
}

/// The project/branch identity plus a live diffstat and a one-click commit —
/// this is real `git` state (see GitStatusProbe), not decoration.
private struct GitStatusBar: View {
    @ObservedObject var state: AppState
    @ObservedObject var git: GitStatusProbe

    private var hasChanges: Bool { git.insertions > 0 || git.deletions > 0 }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "chevron.left.forwardslash.chevron.right")
                .font(.system(size: 10)).foregroundStyle(GeoTheme.inkTertiary)
            Text(URL(fileURLWithPath: state.projectRoot).lastPathComponent)
                .font(GeoTheme.ui(11, .medium)).foregroundStyle(GeoTheme.ink).lineLimit(1)
            if let branch = git.branch {
                Text(branch)
                    .font(GeoTheme.mono(10.5)).foregroundStyle(GeoTheme.inkSecondary)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(GeoTheme.sunken, in: Capsule())
            }
            Spacer(minLength: 6)
            if hasChanges {
                HStack(spacing: 4) {
                    if git.insertions > 0 { Text("+\(git.insertions)").foregroundStyle(GeoTheme.diffAddInk) }
                    if git.deletions > 0 { Text("-\(git.deletions)").foregroundStyle(GeoTheme.diffDelInk) }
                }
                .font(GeoTheme.mono(11, .medium))
            }
            Button("Commit changes") { state.sendMessage("/commit") }
                .font(GeoTheme.ui(10.5, .medium))
                .foregroundStyle(hasChanges ? .white : GeoTheme.inkTertiary)
                .padding(.horizontal, 9).padding(.vertical, 4)
                .background(hasChanges ? GeoTheme.accent : GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 6))
                .buttonStyle(.plain)
                .disabled(!hasChanges)
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
        .overlay(alignment: .top) { Rectangle().fill(GeoTheme.border).frame(height: 1) }
    }
}

