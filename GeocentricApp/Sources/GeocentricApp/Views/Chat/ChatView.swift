import SwiftUI

struct ChatView: View {
    @ObservedObject var state: AppState
    @Binding var draft: String
    let surface: WorkspaceMode

    private var isEmpty: Bool {
        state.timeline.isEmpty && state.activePlan == nil
    }

    var body: some View {
        Group {
            if isEmpty {
                HomeView(state: state, draft: $draft, surface: surface)
            } else {
                conversation
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var conversation: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 11) {
                        ForEach(state.timeline) { entry in
                            row(for: entry).id(entry.id)
                        }
                        if state.busy && !hasStreamingBubble {
                            ThinkingRow(text: state.thinkingHint.isEmpty ? state.agentActivity.label : state.thinkingHint)
                                .id("activity")
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .frame(maxWidth: GeoTheme.composerMaxWidth)
                    .frame(maxWidth: .infinity)
                    .padding(.horizontal, 26)
                    .padding(.vertical, 18)
                }
                .onChange(of: state.timeline.count) {
                    withAnimation(.easeOut(duration: 0.15)) { proxy.scrollTo("bottom", anchor: .bottom) }
                }
            }

            VStack(spacing: 10) {
                if let approval = state.pendingApproval {
                    ApprovalBannerView(request: approval) { state.respondToApproval($0) }
                }
                if let question = state.pendingQuestion {
                    QuestionBannerView(request: question) {
                        state.answerQuestion(option: $0, question: question)
                    }
                }
                if let plan = state.activePlan {
                    PlanView(
                        plan: plan,
                        onAcceptManual: { state.acceptPlan(auto: false) },
                        onAcceptAuto: { state.acceptPlan(auto: true) },
                        onRevise: { state.revisePlan(feedback: $0) },
                        onCancel: { state.cancelPlan() }
                    )
                }
                ComposerCard(
                    state: state,
                    text: $draft,
                    placeholder: "Reply, or type / for a command",
                    perched: false,
                    showProjectButton: false,
                    showTypingCompanion: true
                )
            }
            .frame(maxWidth: GeoTheme.composerMaxWidth)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 26)
            .padding(.bottom, 16)
            .padding(.top, 4)
        }
    }

    /// True once the streaming assistant bubble has appeared, so the thinking
    /// row hands off to it instead of showing both at once.
    private var hasStreamingBubble: Bool {
        state.timeline.last?.kind == .assistantMessage && state.timeline.last?.isStreaming == true
    }

    @ViewBuilder
    private func row(for entry: TimelineEntry) -> some View {
        if entry.kind == .toolCall, let record = entry.toolCall {
            ToolCallCardView(record: record)
        } else {
            MessageBubbleView(entry: entry)
        }
    }
}

/// The original, minimal "thinking…" indicator: a small spinner and a line of
/// text sitting where the reply will land, not a separate floating card.
struct ThinkingRow: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            HStack(spacing: 7) {
                ProgressView().controlSize(.small).scaleEffect(0.8)
                Text(text)
                    .font(GeoTheme.ui(12.5))
                    .foregroundStyle(GeoTheme.inkSecondary)
                    .contentTransition(.opacity)
            }
            .padding(.horizontal, 13).padding(.vertical, 9)
            .background(GeoTheme.canvasWarm, in: RoundedRectangle(cornerRadius: 12))
            Spacer(minLength: 70)
        }
    }
}
