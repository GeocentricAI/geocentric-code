import SwiftUI
import AppKit

/// Loads and caches Geo's frames from the bundled PNGs. Decoding 13 small
/// sprites on every animation tick would be wasteful, so each is read once.
enum GeoSprites {
    private static var cache: [String: NSImage] = [:]

    static func image(named name: String) -> NSImage? {
        if let hit = cache[name] { return hit }
        guard let bundle = AppResources.bundle,
              let url = bundle.url(forResource: name, withExtension: "png", subdirectory: "Sprites")
                ?? bundle.url(forResource: name, withExtension: "png"),
              let image = NSImage(contentsOf: url) else { return nil }
        cache[name] = image
        return image
    }
}

/// Geo, the Geocentric mascot. Plays a different loop for each app moment —
/// typing while the engine works, blinking at rest, glancing while something
/// waits on you, cheering on a clean finish, wincing on an error.
///
/// `height` sizes Geo's *body*, not the image. The typing and celebrating
/// frames include extra canvas (a terminal above him, headroom for raised
/// arms) that isn't part of his body, so his body is a smaller fraction of
/// those canvases; scaling the raw image to a fixed height would make him
/// visibly jump in size when the state changes. These fractions come straight
/// from the sprite generator's layout (see geo_art.swift) and keep his body
/// the same rendered size across every loop.
private let bodyFraction: [MascotStateKey: CGFloat] = [
    .idle: 13.0 / 17.0,
    .pondering: 13.0 / 17.0,
    .active: 11.0 / 33.0,
    .waiting: 13.0 / 17.0,
    .celebrating: 13.0 / 20.0,
    .worried: 13.0 / 17.0,
]

/// A plain, Hashable mirror of MascotState for use as a dictionary key —
/// MascotState itself only needs Equatable for the rest of the app.
private enum MascotStateKey: Hashable {
    case idle, pondering, active, waiting, celebrating, worried

    init(_ state: MascotState) {
        switch state {
        case .idle: self = .idle
        case .pondering: self = .pondering
        case .active: self = .active
        case .waiting: self = .waiting
        case .celebrating: self = .celebrating
        case .worried: self = .worried
        }
    }
}

struct GeoSpriteView: View {
    let state: MascotState
    /// Height of Geo's body. The rendered image may be taller than this.
    var height: CGFloat = 56

    @StateObject private var animator = GeoAnimator()

    /// Full rendered height for a given body height — callers that need to
    /// position Geo relative to other chrome (the composer perch) need this.
    static func imageHeight(state: MascotState, bodyHeight: CGFloat) -> CGFloat {
        bodyHeight / (bodyFraction[MascotStateKey(state)] ?? bodyFraction[.idle]!)
    }

    private var imageHeight: CGFloat {
        Self.imageHeight(state: state, bodyHeight: height)
    }

    var body: some View {
        Group {
            if let nsImage = GeoSprites.image(named: animator.frameName) {
                Image(nsImage: nsImage)
                    .interpolation(.none)   // keep the pixel art crisp
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(height: imageHeight)
                    .fixedSize()
            } else {
                Color.clear.frame(width: height, height: height)
            }
        }
        // Smooth transitions belong at the *state* level (idle → pondering →
        // active), animating the container each state change lands on — not
        // per-frame. An `.id()`-driven crossfade on every single blink/type
        // tick briefly shows neither frame at full opacity, which on an
        // opaque backdrop just looks like a fast blend but on the floating
        // panel's transparent background reads as Geo flickering out for a
        // couple of frames.
        .animation(.linear(duration: 0.2), value: state)
        .onAppear { animator.setState(state) }
        .onChange(of: state) { _, newValue in animator.setState(newValue) }
        .accessibilityLabel(accessibilityLabel)
    }

    private var accessibilityLabel: String {
        switch state {
        case .idle: return "Geo is idle"
        case .pondering: return "Geo is thinking"
        case .active: return "Geo is working"
        case .waiting: return "Geo is waiting for your reply"
        case .celebrating: return "Geo finished successfully"
        case .worried: return "Geo hit an error"
        }
    }
}

/// Geo plus a one-line status, for the sidebar header.
struct GeoStatusView: View {
    let state: MascotState
    let label: String
    var height: CGFloat = 40

    var body: some View {
        HStack(spacing: 9) {
            GeoSpriteView(state: state, height: height)
            VStack(alignment: .leading, spacing: 1) {
                Text("Geo").font(GeoTheme.ui(12, .semibold)).foregroundStyle(GeoTheme.ink)
                Text(label)
                    .font(GeoTheme.ui(11))
                    .foregroundStyle(GeoTheme.inkSecondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
    }
}
