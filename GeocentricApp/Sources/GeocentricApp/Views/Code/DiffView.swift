import SwiftUI

/// Renders a unified diff (as produced by ToolResult.diff) with +/- colouring.
struct DiffTextView: View {
    let diff: String

    private var lines: [String] {
        diff.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                Text(line.isEmpty ? " " : line)
                    .font(GeoTheme.mono(11))
                    .foregroundStyle(ink(for: line))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 6).padding(.vertical, 0.5)
                    .background(fill(for: line))
            }
        }
        .textSelection(.enabled)
    }

    private func isHeader(_ l: String) -> Bool {
        l.hasPrefix("+++") || l.hasPrefix("---") || l.hasPrefix("@@") || l.hasPrefix("diff ")
    }

    private func ink(for line: String) -> Color {
        if line.hasPrefix("@@") { return GeoTheme.plan }
        if isHeader(line) { return GeoTheme.inkTertiary }
        if line.hasPrefix("+") { return GeoTheme.diffAddInk }
        if line.hasPrefix("-") { return GeoTheme.diffDelInk }
        return GeoTheme.ink
    }

    private func fill(for line: String) -> Color {
        if isHeader(line) { return .clear }
        if line.hasPrefix("+") { return GeoTheme.diffAddBg }
        if line.hasPrefix("-") { return GeoTheme.diffDelBg }
        return .clear
    }
}

struct DiffPaneView: View {
    let path: String
    let diff: String

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "plusminus").font(.system(size: 10))
                    .foregroundStyle(GeoTheme.inkSecondary)
                Text(path).font(GeoTheme.mono(11.5, .medium)).foregroundStyle(GeoTheme.ink)
                Spacer()
            }
            .padding(.horizontal, 11).padding(.vertical, 8)
            .background(GeoTheme.canvasWarm)
            .overlay(alignment: .bottom) { Rectangle().fill(GeoTheme.border).frame(height: 1) }

            ScrollView([.horizontal, .vertical]) {
                DiffTextView(diff: diff).padding(.vertical, 8)
            }
            .background(GeoTheme.card)
        }
    }
}
