import SwiftUI

struct PlanView: View {
    @ObservedObject var plan: PlanProposal
    let onAcceptManual: () -> Void
    let onAcceptAuto: () -> Void
    let onRevise: (String) -> Void
    let onCancel: () -> Void

    @State private var feedback = ""
    @State private var showRevise = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 7) {
                Image(systemName: "map.fill").font(.system(size: 11)).foregroundStyle(GeoTheme.plan)
                Text("Proposed plan").font(GeoTheme.ui(13, .semibold)).foregroundStyle(GeoTheme.ink)
                Spacer()
                Text("read-only until you accept")
                    .font(GeoTheme.ui(10.5)).foregroundStyle(GeoTheme.inkTertiary)
            }

            if plan.structured {
                if !plan.goal.isEmpty {
                    Text(plan.goal).font(GeoTheme.ui(13)).foregroundStyle(GeoTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !plan.files.isEmpty {
                    header("Files")
                    ForEach(plan.files, id: \.self) { f in
                        Text("· \(f)").font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkSecondary)
                    }
                }
                if !plan.steps.isEmpty {
                    header("Steps")
                    ForEach(Array(plan.steps.enumerated()), id: \.offset) { i, s in
                        HStack(alignment: .top, spacing: 6) {
                            Text("\(i + 1).").font(GeoTheme.ui(12, .semibold)).foregroundStyle(GeoTheme.accent)
                            Text(s).font(GeoTheme.ui(12.5)).foregroundStyle(GeoTheme.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                if !plan.risks.isEmpty, !["none", "n/a"].contains(plan.risks.lowercased().trimmingCharacters(in: .whitespaces)) {
                    header("Risks")
                    Text(plan.risks).font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.warn)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !plan.verification.isEmpty {
                    header("Verify with")
                    Text(plan.verification).font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkSecondary)
                }
            } else {
                Text(plan.raw).font(GeoTheme.ui(12.5)).foregroundStyle(GeoTheme.ink)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }

            if showRevise {
                HStack(spacing: 7) {
                    TextField("What should change?", text: $feedback)
                        .textFieldStyle(.plain)
                        .font(GeoTheme.ui(12))
                        .padding(.horizontal, 10).padding(.vertical, 6)
                        .background(GeoTheme.canvasWarm, in: RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(GeoTheme.border, lineWidth: 1))
                        .onSubmit(submitRevision)
                    PillButton(title: "Send", kind: .primary, action: submitRevision)
                }
            }

            HStack(spacing: 7) {
                PillButton(title: "Accept — ask each time", kind: .primary, action: onAcceptManual)
                PillButton(title: "Run automatically", action: onAcceptAuto)
                PillButton(title: "Request changes") { showRevise.toggle() }
                PillButton(title: "Cancel", action: onCancel)
                Spacer()
            }
        }
        .padding(14)
        .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: GeoTheme.cardRadius))
        .overlay(RoundedRectangle(cornerRadius: GeoTheme.cardRadius).stroke(GeoTheme.plan.opacity(0.35), lineWidth: 1))
    }

    private func submitRevision() {
        guard !feedback.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        onRevise(feedback)
        feedback = ""
        showRevise = false
    }

    private func header(_ text: String) -> some View {
        Text(text.uppercased())
            .font(GeoTheme.ui(9.5, .bold))
            .foregroundStyle(GeoTheme.inkTertiary)
            .padding(.top, 3)
    }
}
