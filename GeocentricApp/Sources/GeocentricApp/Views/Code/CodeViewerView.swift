import SwiftUI

/// Lightweight regex-based highlighting — good enough for readability without
/// pulling in a full language server. Covers keywords/strings/comments/numbers
/// across the common languages this agent touches.
enum SyntaxHighlighter {
    private static let keywords: Set<String> = [
        "func", "let", "var", "if", "else", "for", "while", "return", "class", "struct",
        "enum", "import", "public", "private", "static", "guard", "switch", "case", "break",
        "continue", "def", "self", "None", "True", "False", "elif", "except", "try", "finally",
        "with", "as", "from", "lambda", "yield", "async", "await", "const", "function", "export",
        "default", "new", "this", "extends", "implements", "interface", "type", "void", "null",
        "undefined", "throw", "catch", "do", "in", "of", "instanceof", "typeof", "package",
        "namespace", "protocol", "fn", "impl", "match", "pub", "use", "mod", "trait",
    ]

    private static let stringPattern = try! NSRegularExpression(pattern: #""(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'"#)
    private static let commentPattern = try! NSRegularExpression(pattern: #"//.*$|#.*$"#, options: [.anchorsMatchLines])
    private static let blockCommentPattern = try! NSRegularExpression(pattern: #"/\*[\s\S]*?\*/"#)
    private static let numberPattern = try! NSRegularExpression(pattern: #"\b\d+\.?\d*\b"#)
    private static let keywordPattern = try! NSRegularExpression(pattern: #"\b[A-Za-z_][A-Za-z0-9_]*\b"#)

    static func highlight(_ code: String) -> AttributedString {
        var attributed = AttributedString(code)
        let ns = code as NSString
        let full = NSRange(location: 0, length: ns.length)

        func apply(_ regex: NSRegularExpression, color: Color, filter: ((String) -> Bool)? = nil) {
            regex.enumerateMatches(in: code, range: full) { match, _, _ in
                guard let match, let range = Range(match.range, in: code) else { return }
                let text = String(code[range])
                if let filter, !filter(text) { return }
                guard let attrRange = Range(range, in: attributed) else { return }
                attributed[attrRange].foregroundColor = color
            }
        }

        apply(keywordPattern, color: GeoTheme.plan, filter: { keywords.contains($0) })
        apply(numberPattern, color: GeoTheme.warn)
        apply(stringPattern, color: GeoTheme.diffDelInk)
        apply(commentPattern, color: GeoTheme.inkTertiary)
        apply(blockCommentPattern, color: GeoTheme.inkTertiary)
        return attributed
    }
}

struct CodeViewerView: View {
    let path: String
    let content: String

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "doc").font(.system(size: 10)).foregroundStyle(GeoTheme.inkSecondary)
                Text(path).font(GeoTheme.mono(11.5, .medium)).foregroundStyle(GeoTheme.ink)
                Spacer()
                Text("\(content.split(separator: "\n", omittingEmptySubsequences: false).count) lines")
                    .font(GeoTheme.ui(10.5)).foregroundStyle(GeoTheme.inkTertiary)
            }
            .padding(.horizontal, 11).padding(.vertical, 8)
            .background(GeoTheme.canvasWarm)
            .overlay(alignment: .bottom) { Rectangle().fill(GeoTheme.border).frame(height: 1) }

            ScrollView([.horizontal, .vertical]) {
                HStack(alignment: .top, spacing: 10) {
                    lineNumbers
                    Text(SyntaxHighlighter.highlight(content))
                        .font(GeoTheme.mono(11.5))
                        .textSelection(.enabled)
                }
                .padding(.horizontal, 10).padding(.vertical, 9)
            }
            .background(GeoTheme.card)
        }
    }

    private var lineNumbers: some View {
        let count = max(content.split(separator: "\n", omittingEmptySubsequences: false).count, 1)
        return VStack(alignment: .trailing, spacing: 0) {
            ForEach(1...count, id: \.self) { n in
                Text("\(n)")
                    .font(GeoTheme.mono(11.5))
                    .foregroundStyle(GeoTheme.inkTertiary)
            }
        }
    }
}
