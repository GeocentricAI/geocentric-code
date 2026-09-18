import SwiftUI

/// The Geocentric mark: a calligraphic G, solid ink against the paper canvas —
/// no gradient sweep or sparkle dust. Plain enough to sit quietly next to the
/// serif greeting rather than compete with it.
struct GeoLogo: View {
    var size: CGFloat = 34

    private var font: Font {
        // Snell Roundhand ships with macOS; fall back to a serif if it is ever
        // unavailable so the mark degrades to something still typographic.
        if NSFont(name: "SnellRoundhand-Black", size: size) != nil {
            return .custom("SnellRoundhand-Black", size: size)
        }
        return .system(size: size, weight: .bold, design: .serif)
    }

    var body: some View {
        Text("G")
            .font(font)
            .foregroundStyle(GeoTheme.ink)
            .fixedSize()
            .accessibilityLabel("Geocentric")
    }
}
