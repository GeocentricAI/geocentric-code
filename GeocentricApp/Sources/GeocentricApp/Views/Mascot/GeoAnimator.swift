import Foundation
import Combine

/// Drives Geo's sprite loops. Every state loops continuously while it's
/// current — celebrating/worried are triggered as short-lived states by
/// AppState (see `flashMascot`), not one-shot animations played out here, so
/// this stays a single uniform looping model instead of two different timing
/// systems.
@MainActor
final class GeoAnimator: ObservableObject {
    @Published private(set) var frameName: String = "geo_blink_1"

    private var timer: Timer?
    private var state: MascotState = .idle
    private var idleFrame = 0          // 0 = resting; 1...4 mid-blink (frames 2-5)
    private var loopFrame = 0          // generic index into whichever loop is active
    private var ticksUntilNextBlink = 0

    private let idleFrames = ["geo_blink_1", "geo_blink_2", "geo_blink_3", "geo_blink_4", "geo_blink_5"]
    private let typeFrames = ["geo_type_1", "geo_type_2", "geo_type_3", "geo_type_4",
                               "geo_type_5", "geo_type_6", "geo_type_7", "geo_type_8"]
    private let waitFrames = ["geo_wait_1", "geo_wait_2", "geo_wait_3", "geo_wait_4"]
    private let yayFrames = ["geo_yay_1", "geo_yay_2", "geo_yay_3", "geo_yay_4", "geo_yay_5"]
    private let worriedFrames = ["geo_worried_1", "geo_worried_2", "geo_worried_3", "geo_worried_4"]

    init() {
        scheduleNextBlink()
        let t = Timer(timeInterval: 0.12, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
        // `Timer.scheduledTimer` only runs in the `.default` run loop mode,
        // which macOS suspends for the duration of any interactive mouse
        // tracking (dragging the floating panel included). The timer doesn't
        // stop, it *queues up* the missed fires — so the instant tracking
        // ends, they all land at once and Geo appears to replay several
        // frames of animation in a burst. Adding it to `.common` keeps it
        // ticking through tracking loops instead of falling behind.
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    func setState(_ newState: MascotState) {
        guard newState != state else { return }
        state = newState
        loopFrame = 0
        switch newState {
        case .idle:
            idleFrame = 0
            frameName = idleFrames[0]
            scheduleNextBlink()
        case .active:
            frameName = typeFrames[0]
        case .pondering, .waiting:
            frameName = waitFrames[0]
        case .celebrating:
            frameName = yayFrames[0]
        case .worried:
            frameName = worriedFrames[0]
        }
    }

    private func scheduleNextBlink() {
        // ~4.5s between blinks, roughly (blink tick fires every ~0.12s * ~38 ticks).
        ticksUntilNextBlink = Int.random(in: 28...48)
    }

    private func tick() {
        switch state {
        case .active:
            loopFrame = (loopFrame + 1) % typeFrames.count
            frameName = typeFrames[loopFrame]
        case .pondering, .waiting:
            // Slower than the other loops — a glance every ~0.7s reads as
            // "looking over at you" (waiting) or "considering it" (pondering),
            // not a nervous twitch.
            loopFrame += 1
            if loopFrame % 6 == 0 {
                frameName = waitFrames[(loopFrame / 6) % waitFrames.count]
            }
        case .celebrating:
            loopFrame = (loopFrame + 1) % yayFrames.count
            frameName = yayFrames[loopFrame]
        case .worried:
            loopFrame = (loopFrame + 1) % worriedFrames.count
            frameName = worriedFrames[loopFrame]
        case .idle:
            if idleFrame == 0 {
                ticksUntilNextBlink -= 1
                if ticksUntilNextBlink <= 0 {
                    idleFrame = 1
                    frameName = idleFrames[idleFrame]
                }
            } else {
                idleFrame += 1
                if idleFrame >= idleFrames.count {
                    idleFrame = 0
                    frameName = idleFrames[0]
                    scheduleNextBlink()
                } else {
                    frameName = idleFrames[idleFrame]
                }
            }
        }
    }

    deinit {
        timer?.invalidate()
    }
}
