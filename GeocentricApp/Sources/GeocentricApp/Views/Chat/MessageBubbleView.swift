import SwiftUI
import AppKit

struct MessageBubbleView: View {
    @ObservedObject var entry: TimelineEntry

    var body: some View {
        switch entry.kind {
        case .userMessage:
            HStack {
                Spacer(minLength: 70)
                Text(entry.text)
                    .font(GeoTheme.ui(13.5))
                    .foregroundStyle(GeoTheme.ink)
                    .textSelection(.enabled)
                    .padding(.horizontal, 13).padding(.vertical, 9)
                    .background(GeoTheme.accentWash, in: RoundedRectangle(cornerRadius: 13))
                    .overlay(RoundedRectangle(cornerRadius: 13).stroke(GeoTheme.accentSoft.opacity(0.6), lineWidth: 1))
            }

        case .assistantMessage:
            HStack(alignment: .top, spacing: 0) {
                // Live progress belongs to ThinkingRow, which is tied to the
                // current turn rather than any one bubble. A message bubble
                // only ever shows settled text, so a turn that dies mid-flight
                // can't strand a permanently "thinking" row in the transcript.
                VStack(alignment: .leading, spacing: 7) {
                    if !entry.text.isEmpty {
                        if !entry.thinkingText.isEmpty {
                            ThoughtProcessDisclosure(text: entry.thinkingText)
                        }
                        MarkdownishText(entry.text)
                        CopyButton(text: entry.text)
                    }
                }
                Spacer(minLength: 70)
            }

        case .commandOutput:
            HStack {
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(entry.text)
                        .font(GeoTheme.mono(11.5))
                        .foregroundStyle(GeoTheme.ink)
                        .textSelection(.enabled)
                }
                .padding(11)
                .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: GeoTheme.cardRadius))
                Spacer(minLength: 50)
            }

        case .note:
            HStack(spacing: 6) {
                Image(systemName: noteIcon).font(.system(size: 11))
                Text(entry.text).font(GeoTheme.ui(12)).textSelection(.enabled)
                Spacer()
            }
            .foregroundStyle(noteColor)
            .padding(.vertical, 1)

        case .toolCall, .planProposal:
            EmptyView()
        }
    }

    private var noteIcon: String {
        switch entry.style {
        case .error: return "exclamationmark.octagon"
        case .warn: return "exclamationmark.triangle"
        case .success: return "checkmark.circle"
        case .info: return "info.circle"
        }
    }

    private var noteColor: Color {
        switch entry.style {
        case .error: return GeoTheme.danger
        case .warn: return GeoTheme.warn
        case .success: return GeoTheme.success
        case .info: return GeoTheme.inkSecondary
        }
    }
}

/// A small "Copy" affordance under a settled assistant reply — copies the raw
/// Markdown source, not a screenshot of the rendered text, since that's what's
/// actually useful to paste elsewhere.
struct CopyButton: View {
    let text: String
    @State private var copied = false

    var body: some View {
        Button {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(text, forType: .string)
            copied = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { copied = false }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    .font(.system(size: 10))
                Text(copied ? "Copied" : "Copy")
                    .font(GeoTheme.ui(10.5, .medium))
            }
            .foregroundStyle(copied ? GeoTheme.success : GeoTheme.inkTertiary)
        }
        .buttonStyle(.plain)
    }
}

/// A collapsed-by-default "Thought process ›" disclosure sitting above the
/// settled reply. The raw reasoning stream is noisy and often incomplete, so
/// it stays tucked away unless you actually want to see it.
struct ThoughtProcessDisclosure: View {
    let text: String
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button { withAnimation(.easeOut(duration: 0.15)) { expanded.toggle() } } label: {
                HStack(spacing: 5) {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 8, weight: .semibold))
                        .rotationEffect(.degrees(expanded ? 90 : 0))
                    Text("Thought process")
                        .font(GeoTheme.ui(11, .medium))
                }
                .foregroundStyle(GeoTheme.inkTertiary)
            }
            .buttonStyle(.plain)

            if expanded {
                Text(text)
                    .font(GeoTheme.ui(11.5))
                    .foregroundStyle(GeoTheme.inkSecondary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(9)
                    .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }
}

struct GlowingBrainIcon: View {
    @State private var phase: Double = 0

    var body: some View {
        Image(systemName: "brain")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(GeoTheme.accent)
            .opacity(0.6 + (sin(phase) * 0.4))
            .shadow(color: GeoTheme.accent.opacity(0.5), radius: 3)
            .onAppear {
                withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
                    phase = .pi
                }
            }
    }
}

// MarkdownishText now lives in RichMarkdown.swift, with real block-level
// Markdown parsing and KaTeX-backed math rendering (see MathView.swift).
