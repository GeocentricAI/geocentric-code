import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}

/// Warm, paper-toned palette. Deliberately light-only: the whole look depends on
/// the cream canvas, so the app pins its appearance rather than half-supporting
/// a dark mode that would fight it.
enum GeoTheme {
    // Surfaces
    static let canvas = Color(hex: 0xF5F4EE)       // app background
    static let canvasWarm = Color(hex: 0xFAF9F5)   // elevated panels
    static let card = Color.white                  // interactive cards
    static let rail = Color(hex: 0xF0EEE6)         // icon rail
    static let sunken = Color(hex: 0xEFEDE4)       // wells, code gutters

    // Ink
    static let ink = Color(hex: 0x1F1E1D)
    static let inkSecondary = Color(hex: 0x7D7A73)
    static let inkTertiary = Color(hex: 0xA8A49B)

    // Accent — warm coral, the one saturated colour in the palette
    static let accent = Color(hex: 0xD97757)
    static let accentSoft = Color(hex: 0xF0C3B0)
    static let accentWash = Color(hex: 0xFAEDE6)

    // Lines
    static let border = Color(hex: 0xE6E3DA)
    static let borderStrong = Color(hex: 0xD6D2C7)

    // Semantic — muted to sit against paper rather than glow against black
    static let danger = Color(hex: 0xC0392B)
    static let warn = Color(hex: 0xB8791F)
    static let success = Color(hex: 0x4F7A44)
    static let plan = Color(hex: 0x6B5B95)

    // Diff
    static let diffAddBg = Color(hex: 0xE8F2E4)
    static let diffAddInk = Color(hex: 0x3D6B33)
    static let diffDelBg = Color(hex: 0xFAE7E4)
    static let diffDelInk = Color(hex: 0xA8443A)

    // Type. The serif is load-bearing: it carries the app's character in
    // greetings and empty states. Do not swap it for the system sans.
    static func serif(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }
    static func ui(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight)
    }
    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }

    // Metrics
    static let composerRadius: CGFloat = 18
    static let cardRadius: CGFloat = 12
    static let railWidth: CGFloat = 56
    static let composerMaxWidth: CGFloat = 760
}

/// The faint dot grid behind the Code surface.
struct DotGridBackground: View {
    var spacing: CGFloat = 22
    var body: some View {
        Canvas { context, size in
            let dot = CGSize(width: 1.5, height: 1.5)
            let color = GraphicsContext.Shading.color(GeoTheme.borderStrong.opacity(0.55))
            var y: CGFloat = spacing / 2
            while y < size.height {
                var x: CGFloat = spacing / 2
                while x < size.width {
                    context.fill(Path(ellipseIn: CGRect(origin: CGPoint(x: x, y: y), size: dot)), with: color)
                    x += spacing
                }
                y += spacing
            }
        }
        .drawingGroup()
        .allowsHitTesting(false)
    }
}
