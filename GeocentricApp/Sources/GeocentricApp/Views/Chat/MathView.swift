import SwiftUI
import WebKit

/// Renders one LaTeX expression via a bundled, offline copy of KaTeX in a
/// borderless WKWebView. Real math typesetting — fractions, radicals, sums,
/// matrices — rather than a Unicode approximation, and it needs no network
/// access since katex.min.js/css/fonts all ship in the app bundle.
struct MathView: View {
    let latex: String
    var displayMode: Bool = false

    @State private var size = CGSize(width: 24, height: 20)

    var body: some View {
        KaTeXWebView(latex: latex, displayMode: displayMode) { measured in
            guard measured.width > 0, measured.height > 0 else { return }
            size = measured
        }
        .frame(width: size.width, height: size.height)
        // KaTeX renders red "parse error" text inline when it can't read an
        // expression; that's KaTeX's own error styling, left as-is rather
        // than hidden, since it's genuinely useful feedback on malformed TeX.
    }
}

private struct KaTeXWebView: NSViewRepresentable {
    let latex: String
    let displayMode: Bool
    let onSize: (CGSize) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onSize: onSize) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        webView.navigationDelegate = context.coordinator
        context.coordinator.load(latex: latex, displayMode: displayMode, into: webView)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        context.coordinator.onSize = onSize
        guard context.coordinator.lastLatex != latex || context.coordinator.lastDisplayMode != displayMode else { return }
        context.coordinator.load(latex: latex, displayMode: displayMode, into: webView)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var onSize: (CGSize) -> Void
        fileprivate var lastLatex: String?
        fileprivate var lastDisplayMode: Bool?

        init(onSize: @escaping (CGSize) -> Void) {
            self.onSize = onSize
        }

        func load(latex: String, displayMode: Bool, into webView: WKWebView) {
            lastLatex = latex
            lastDisplayMode = displayMode
            guard let bundle = AppResources.bundle,
                  let katexDir = bundle.url(forResource: "katex.min", withExtension: "css", subdirectory: "KaTeX")?
                .deletingLastPathComponent() else { return }

            // JSON-encoding the LaTeX source (rather than splicing it into a
            // template literal) is what makes this safe against expressions
            // containing backslashes, quotes, or stray backticks.
            let jsonLatex = (try? String(data: JSONEncoder().encode(latex), encoding: .utf8)) ?? "\"\""

            let html = """
            <!doctype html><html><head><meta charset="utf-8">
            <link rel="stylesheet" href="katex.min.css">
            <style>
              html, body { margin: 0; padding: 0; background: transparent; overflow: hidden; }
              #root { display: inline-block; font-size: 16px; color: #1F1E1D; }
              .katex-display { margin: 0; }
              .katex-error { color: #C0392B; }
            </style>
            </head><body>
            <div id="root"></div>
            <script src="katex.min.js"></script>
            <script>
              katex.render(\(jsonLatex), document.getElementById('root'), {
                throwOnError: false,
                displayMode: \(displayMode ? "true" : "false")
              });
            </script>
            </body></html>
            """
            webView.loadHTMLString(html, baseURL: katexDir)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            webView.evaluateJavaScript("""
                (function() {
                    var r = document.getElementById('root').getBoundingClientRect();
                    return [r.width, r.height];
                })()
            """) { [weak self] result, _ in
                guard let pair = result as? [Double], pair.count == 2 else { return }
                self?.onSize(CGSize(width: ceil(pair[0]) + 2, height: ceil(pair[1]) + 2))
            }
        }
    }
}
