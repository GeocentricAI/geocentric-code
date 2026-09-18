import SwiftUI
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        // The whole design rests on the warm paper canvas; a system dark mode
        // would fight it rather than adapt, so the appearance is pinned.
        NSApp.appearance = NSAppearance(named: .aqua)
        NSApp.activate(ignoringOtherApps: true)

        configureWindow()
        // SwiftUI restores the saved frame *after* launch finishes, so a stale
        // or off-screen frame wins unless the correction runs on the next pass.
        DispatchQueue.main.async { [weak self] in self?.configureWindow() }
    }

    private func configureWindow() {
        guard let window = NSApp.windows.first else { return }
        window.titlebarAppearsTransparent = true
        // Matches GeoTheme.rail (0xF0EEE6), not the canvas — the traffic
        // lights sit directly over the rail, so this is whatever shows
        // through in the sliver before SwiftUI's own content paints.
        window.backgroundColor = NSColor(red: 0.941, green: 0.933, blue: 0.902, alpha: 1)

        guard let screen = window.screen ?? NSScreen.main else { return }
        let visible = screen.visibleFrame

        // Only intervene when the restored frame is unusable — otherwise the
        // user's own window placement is respected across launches.
        let fitsOnScreen = visible.insetBy(dx: -8, dy: -8).contains(window.frame)
        guard !fitsOnScreen || window.frame.width < 900 || window.frame.height < 600 else { return }

        let width = min(1180, visible.width - 120)
        let height = min(780, visible.height - 120)
        window.setFrame(
            NSRect(x: visible.midX - width / 2,
                   y: visible.midY - height / 2,
                   width: width, height: height),
            display: true
        )
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main
struct GeocentricMacApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            RootView()
                .frame(minWidth: 980, minHeight: 660)
                .preferredColorScheme(.light)
        }
        .windowStyle(.hiddenTitleBar)
        .windowToolbarStyle(.unifiedCompact(showsTitle: false))
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("New conversation") { }
                    .keyboardShortcut("n", modifiers: .command)
            }
        }
    }
}
