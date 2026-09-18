import SwiftUI

struct ToolLogView: View {
    let entries: [TimelineEntry]

    private var toolEntries: [TimelineEntry] {
        entries.filter { $0.kind == .toolCall && $0.toolCall != nil }
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 6) {
                if toolEntries.isEmpty {
                    VStack(spacing: 6) {
                        Image(systemName: "wrench.and.screwdriver")
                            .font(.system(size: 18)).foregroundStyle(GeoTheme.inkTertiary)
                        Text("No tool activity yet.")
                            .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkTertiary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 50)
                }
                ForEach(toolEntries) { entry in
                    if let record = entry.toolCall {
                        ToolCallCardView(record: record)
                    }
                }
            }
            .padding(11)
        }
        .background(GeoTheme.canvas)
    }
}
