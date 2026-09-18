import SwiftUI

struct ToolCallCardView: View {
    @ObservedObject var record: ToolCallRecord
    @State private var expanded = false
    @State private var hovering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 8) {
                statusIcon.frame(width: 14)

                Text(record.name)
                    .font(GeoTheme.mono(12, .medium))
                    .foregroundStyle(GeoTheme.ink)

                if !record.argsText.isEmpty {
                    Text(record.argsText)
                        .font(GeoTheme.mono(11))
                        .foregroundStyle(GeoTheme.inkTertiary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                Spacer(minLength: 4)

                if record.danger != "low" {
                    Text(record.danger)
                        .font(GeoTheme.ui(9, .bold))
                        .foregroundStyle(record.danger == "high" ? GeoTheme.danger : GeoTheme.warn)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(
                            (record.danger == "high" ? GeoTheme.danger : GeoTheme.warn).opacity(0.12),
                            in: Capsule()
                        )
                }

                if hasDetail {
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(GeoTheme.inkTertiary)
                }
            }
            .padding(.horizontal, 11)
            .padding(.vertical, 9)

            if expanded, hasDetail {
                Divider().overlay(GeoTheme.border)
                VStack(alignment: .leading, spacing: 8) {
                    if let diff = record.diffText, !diff.isEmpty {
                        DiffTextView(diff: diff)
                    } else if !record.outputText.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            Text(record.outputText)
                                .font(GeoTheme.mono(11))
                                .foregroundStyle(record.status == .failed ? GeoTheme.danger : GeoTheme.inkSecondary)
                                .textSelection(.enabled)
                                .lineLimit(40)
                        }
                    }
                }
                .padding(11)
            }
        }
        .background(hovering ? GeoTheme.canvasWarm : GeoTheme.card,
                    in: RoundedRectangle(cornerRadius: GeoTheme.cardRadius))
        .overlay(RoundedRectangle(cornerRadius: GeoTheme.cardRadius).stroke(GeoTheme.border, lineWidth: 1))
        .contentShape(Rectangle())
        .onTapGesture { if hasDetail { withAnimation(.easeOut(duration: 0.12)) { expanded.toggle() } } }
        .onHover { hovering = $0 }
    }

    private var hasDetail: Bool {
        !(record.diffText ?? "").isEmpty || !record.outputText.isEmpty
    }

    @ViewBuilder
    private var statusIcon: some View {
        switch record.status {
        case .running:
            ProgressView().controlSize(.small).scaleEffect(0.6)
        case .ok:
            Image(systemName: "checkmark").font(.system(size: 10, weight: .bold))
                .foregroundStyle(GeoTheme.success)
        case .failed:
            Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                .foregroundStyle(GeoTheme.danger)
        }
    }
}
