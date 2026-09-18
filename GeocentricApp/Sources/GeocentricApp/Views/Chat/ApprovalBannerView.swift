import SwiftUI

struct ApprovalBannerView: View {
    let request: ApprovalRequest
    let onDecision: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 7) {
                Image(systemName: request.danger == "high" ? "exclamationmark.octagon.fill" : "hand.raised.fill")
                    .font(.system(size: 12)).foregroundStyle(tint)
                Text("Approve \(request.tool)?")
                    .font(GeoTheme.ui(13, .semibold)).foregroundStyle(GeoTheme.ink)
                Spacer()
            }
            if !request.argsText.isEmpty {
                Text(request.argsText)
                    .font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkSecondary)
                    .lineLimit(3)
            }
            ForEach(request.reasons, id: \.self) { reason in
                HStack(spacing: 5) {
                    Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9))
                    Text(reason).font(GeoTheme.ui(11.5))
                }
                .foregroundStyle(GeoTheme.warn)
            }
            HStack(spacing: 7) {
                PillButton(title: "Approve once", kind: .primary) { onDecision("once") }
                PillButton(title: "Always allow", kind: .secondary) { onDecision("always") }
                PillButton(title: "Deny", kind: .danger) { onDecision("deny") }
                Spacer()
            }
        }
        .padding(13)
        .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: GeoTheme.cardRadius))
        .overlay(RoundedRectangle(cornerRadius: GeoTheme.cardRadius).stroke(tint.opacity(0.4), lineWidth: 1))
    }

    private var tint: Color {
        request.danger == "high" ? GeoTheme.danger : (request.danger == "medium" ? GeoTheme.warn : GeoTheme.accent)
    }
}

struct QuestionBannerView: View {
    let request: QuestionRequest
    let onAnswer: (QuestionOption) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 7) {
                Image(systemName: "questionmark.circle.fill")
                    .font(.system(size: 12)).foregroundStyle(GeoTheme.accent)
                Text(request.question)
                    .font(GeoTheme.ui(13, .semibold)).foregroundStyle(GeoTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(request.options) { option in
                Button { onAnswer(option) } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(option.label).font(GeoTheme.ui(12.5, .medium)).foregroundStyle(GeoTheme.ink)
                        if !option.description.isEmpty {
                            Text(option.description)
                                .font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkSecondary)
                                .multilineTextAlignment(.leading)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 11).padding(.vertical, 8)
                    .background(GeoTheme.canvasWarm, in: RoundedRectangle(cornerRadius: 9))
                    .overlay(RoundedRectangle(cornerRadius: 9).stroke(GeoTheme.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(13)
        .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: GeoTheme.cardRadius))
        .overlay(RoundedRectangle(cornerRadius: GeoTheme.cardRadius).stroke(GeoTheme.accentSoft, lineWidth: 1))
    }
}

struct PillButton: View {
    enum Kind { case primary, secondary, danger }
    let title: String
    var kind: Kind = .secondary
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(GeoTheme.ui(12, .medium))
                .foregroundStyle(kind == .primary ? .white : (kind == .danger ? GeoTheme.danger : GeoTheme.ink))
                .padding(.horizontal, 13).padding(.vertical, 6)
                .background(background, in: Capsule())
                .overlay(Capsule().stroke(kind == .primary ? .clear : GeoTheme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
    }

    private var background: Color {
        switch kind {
        case .primary: return hovering ? GeoTheme.accent.opacity(0.88) : GeoTheme.accent
        case .danger: return hovering ? GeoTheme.diffDelBg : GeoTheme.card
        case .secondary: return hovering ? GeoTheme.canvasWarm : GeoTheme.card
        }
    }
}
