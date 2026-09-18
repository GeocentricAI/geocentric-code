import SwiftUI
import AppKit

/// Geo, detached into his own borderless panel that floats above every other
/// window (including other apps') instead of living inside the main window.
/// A singleton because there is only ever one Geo — toggling the setting
/// on/off just shows or hides the same panel.
@MainActor
final class GeoFloatingPanel: ObservableObject {
    static let shared = GeoFloatingPanel()

    /// Drives the dizzy eyes + wiggle while the panel is being dragged.
    @Published private(set) var isDragging = false

    private var panel: NSPanel?

    private init() {}

    func setVisible(_ visible: Bool, state: AppState) {
        if visible {
            show(state: state)
        } else {
            panel?.orderOut(nil)
        }
    }

    private func show(state: AppState) {
        if panel == nil {
            let size: CGFloat = 88
            let p = NSPanel(
                contentRect: NSRect(x: 0, y: 0, width: size, height: size),
                styleMask: [.nonactivatingPanel, .borderless, .resizable],
                backing: .buffered,
                defer: false
            )
            p.isFloatingPanel = true
            p.level = .floating
            p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
            p.isOpaque = false
            p.backgroundColor = .clear
            p.hasShadow = true
            // Dragged via DragTrackingHostingView's raw mouse events below,
            // not this — see that class for why.
            p.isMovableByWindowBackground = false
            p.hidesOnDeactivate = false
            // Without this, macOS's own window-restoration brings an orphaned
            // copy of this panel back on the *next* launch regardless of the
            // "float over every window" setting — it's OS-level state, not
            // anything this app's own code decided to do.
            p.isRestorable = false
            let hosting = DragTrackingHostingView(rootView: GeoFloatingView(state: state))
            hosting.onDragChanged = { [weak self] dragging in self?.isDragging = dragging }
            p.contentView = hosting

            if let screen = NSScreen.main {
                let frame = screen.visibleFrame
                p.setFrameOrigin(NSPoint(x: frame.maxX - size - 28, y: frame.minY + 28))
            }
            panel = p
        }
        panel?.orderFrontRegardless()
    }
}

/// Moves its own window by tracking raw mouse events directly, rather than a
/// SwiftUI `DragGesture`.
///
/// A `DragGesture`'s `translation` is reported relative to where the drag
/// *started*, in the view's local coordinate space — but repositioning the
/// window on every update (as dragging it requires) moves that local space
/// out from under the same gesture that's still tracking it. The result is a
/// feedback loop: the reported translation and the window's actual screen
/// position drift apart, which reads as Geo lagging behind the cursor, and
/// occasionally as the gesture never seeing its `onEnded` at all (SwiftUI
/// loses track of the touch in the shifting frame), leaving `isDragging` -
/// and the wiggle animation it drives - stuck on permanently.
///
/// Tracking `NSEvent.mouseLocation` (screen coordinates, which never move)
/// and applying only the *incremental* delta since the last event sidesteps
/// the moving-frame problem entirely, and a real `mouseUp` is unambiguous -
/// there's no gesture-recognition state to get stuck in.
private final class DragTrackingHostingView<Content: View>: NSHostingView<Content> {
    var onDragChanged: ((Bool) -> Void)?
    private var lastScreenPoint: NSPoint?

    override func mouseDown(with event: NSEvent) {
        lastScreenPoint = NSEvent.mouseLocation
        onDragChanged?(true)
    }

    override func mouseDragged(with event: NSEvent) {
        guard let last = lastScreenPoint, let window else { return }
        let current = NSEvent.mouseLocation
        var origin = window.frame.origin
        origin.x += current.x - last.x
        origin.y += current.y - last.y
        window.setFrameOrigin(origin)
        lastScreenPoint = current
    }

    override func mouseUp(with event: NSEvent) {
        lastScreenPoint = nil
        onDragChanged?(false)
    }
}

/// The panel's content: just Geo, reflecting whatever pose the app state is
/// currently in, with an idle loop when nothing else is happening — and a
/// dizzy, wiggling look while you're actually dragging him around.
private struct GeoFloatingView: View {
    @ObservedObject var state: AppState
    @ObservedObject private var panel = GeoFloatingPanel.shared
    @State private var wiggle = false

    var body: some View {
        ZStack {
            GeoSpriteView(state: state.mascotState, height: 60)
                .rotationEffect(.degrees(panel.isDragging ? (wiggle ? 8 : -8) : 0))
                .offset(y: panel.isDragging ? (wiggle ? -2 : 2) : 0)

            if panel.isDragging {
                dizzyEyes
            }
        }
        .frame(width: 88, height: 88)
        .animation(.linear(duration: 0.2), value: state.mascotState)
        .animation(panel.isDragging ? .easeInOut(duration: 0.11).repeatForever(autoreverses: true) : .default, value: wiggle)
        .onChange(of: panel.isDragging) { _, dragging in
            wiggle = dragging
        }
    }

    /// Approximated over the idle/waiting frames' eye position — the sprite
    /// is pixel art with no exposed eye coordinates, so this is a calibrated
    /// guess, not a precise mask.
    private var dizzyEyes: some View {
        GeometryReader { geo in
            HStack(spacing: geo.size.width * 0.16) {
                Text(">").frame(width: geo.size.width * 0.1)
                Text("<").frame(width: geo.size.width * 0.1)
            }
            .font(.system(size: geo.size.height * 0.13, weight: .black, design: .monospaced))
            .foregroundStyle(.black)
            .position(x: geo.size.width * 0.5, y: geo.size.height * 0.46)
        }
        .allowsHitTesting(false)
    }
}
