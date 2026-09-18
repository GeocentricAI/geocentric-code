import Foundation

/// A defensive stand-in for SwiftPM's auto-generated `Bundle.module`.
///
/// `Bundle.module` is a `static let` whose initializer calls `fatalError` if
/// it can't locate the resource bundle — and since `fatalError` can't be
/// caught, any environment where that lookup fails (observed: a fresh
/// install on a different Mac, most likely Gatekeeper's app-translocation
/// running this copy from a randomized read-only path where the generated
/// candidate list doesn't line up) takes the *entire app* down before a
/// single frame renders. Sprites, KaTeX, and the bundled Python engine all
/// go through this instead: same candidate search SwiftPM's generated code
/// does, but a nil on failure rather than a crash — Geo just doesn't render
/// that frame instead of the app dying.
enum AppResources {
    static let bundle: Bundle? = {
        let bundleName = "GeocentricApp_GeocentricApp.bundle"
        let mainBundle = Bundle.main
        let exeDir = mainBundle.executableURL?.deletingLastPathComponent()

        let candidates: [URL?] = [
            mainBundle.resourceURL,                                   // normal .app: Contents/Resources
            mainBundle.bundleURL,                                     // resources sitting at the bundle root
            exeDir,                                                   // right next to the executable (raw SPM build)
            exeDir?.deletingLastPathComponent().appendingPathComponent("Resources"),
        ]

        for case let candidate? in candidates {
            let url = candidate.appendingPathComponent(bundleName)
            if let bundle = Bundle(url: url) {
                return bundle
            }
        }
        return nil
    }()
}
