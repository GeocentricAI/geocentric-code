// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "GeocentricApp",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "GeocentricApp",
            // Loose PNGs, deliberately: SwiftPM copies an .xcassets verbatim
            // rather than running actool on it, so catalog-name lookups never
            // resolve outside an Xcode project.
            resources: [
                .copy("Resources/Sprites"),
                // Bundled KaTeX (CSS/JS/fonts), loaded into a local WKWebView
                // for real math rendering — no network access needed at runtime.
                .copy("Resources/KaTeX"),
                // The Python backend, bundled so a downloaded release is
                // self-contained — install.sh (and first-launch setup) copy
                // this out into a real venv rather than the app depending on
                // the source living anywhere in particular on disk.
                .copy("Resources/PythonEngine")
            ],
            // Backs the Database desk's real SQLite querying — macOS ships
            // libsqlite3 system-wide, this just links against it.
            linkerSettings: [
                .linkedLibrary("sqlite3")
            ]
        )
    ]
)
