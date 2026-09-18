import SwiftUI

/// Renders assistant text as real Markdown plus real math, not an approximation
/// of either. Block structure (headings, lists, quotes, code, `$$…$$` math) is
/// parsed by hand since AttributedString's own Markdown support only covers
/// inline runs; each inline run is then handed to AttributedString(markdown:)
/// for bold/italic/links/code, with `$…$` math spliced out and rendered by
/// MathView (see MathView.swift) instead of shown as raw TeX source.
struct MarkdownishText: View {
    let raw: String

    init(_ raw: String) { self.raw = raw }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(MarkdownParser.parse(raw).enumerated()), id: \.offset) { _, block in
                BlockView(block: block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Block model

private enum MarkdownBlock {
    case heading(level: Int, text: String)
    case paragraph(text: String)
    case bulletList(items: [String])
    case numberedList(items: [String])
    case blockquote(text: String)
    case codeBlock(language: String, text: String)
    case mathBlock(latex: String)
    case rule
}

private enum MarkdownParser {
    static func parse(_ raw: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        let lines = raw.components(separatedBy: "\n")
        var i = 0

        func flushParagraph(_ buffer: inout [String]) {
            guard !buffer.isEmpty else { return }
            let text = buffer.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty { blocks.append(.paragraph(text: text)) }
            buffer = []
        }

        var paragraphBuffer: [String] = []

        while i < lines.count {
            let line = lines[i]
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            if trimmed.hasPrefix("```") {
                flushParagraph(&paragraphBuffer)
                let language = String(trimmed.dropFirst(3))
                var body: [String] = []
                i += 1
                while i < lines.count, !lines[i].trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                    body.append(lines[i])
                    i += 1
                }
                blocks.append(.codeBlock(language: language, text: body.joined(separator: "\n")))
                i += 1
                continue
            }

            if trimmed == "$$" {
                flushParagraph(&paragraphBuffer)
                var body: [String] = []
                i += 1
                while i < lines.count, lines[i].trimmingCharacters(in: .whitespaces) != "$$" {
                    body.append(lines[i])
                    i += 1
                }
                blocks.append(.mathBlock(latex: body.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)))
                i += 1
                continue
            }
            if trimmed.hasPrefix("$$"), trimmed.hasSuffix("$$"), trimmed.count > 4 {
                flushParagraph(&paragraphBuffer)
                blocks.append(.mathBlock(latex: String(trimmed.dropFirst(2).dropLast(2))))
                i += 1
                continue
            }

            if let level = headingLevel(trimmed) {
                flushParagraph(&paragraphBuffer)
                blocks.append(.heading(level: level, text: String(trimmed.dropFirst(level + 1))))
                i += 1
                continue
            }

            if trimmed == "---" || trimmed == "***" || trimmed == "___" {
                flushParagraph(&paragraphBuffer)
                blocks.append(.rule)
                i += 1
                continue
            }

            if trimmed.hasPrefix("> ") || trimmed == ">" {
                flushParagraph(&paragraphBuffer)
                var body: [String] = []
                while i < lines.count {
                    let t = lines[i].trimmingCharacters(in: .whitespaces)
                    guard t.hasPrefix(">") else { break }
                    body.append(String(t.dropFirst(t.hasPrefix("> ") ? 2 : 1)))
                    i += 1
                }
                blocks.append(.blockquote(text: body.joined(separator: "\n")))
                continue
            }

            if isBullet(trimmed) {
                flushParagraph(&paragraphBuffer)
                var items: [String] = []
                while i < lines.count, isBullet(lines[i].trimmingCharacters(in: .whitespaces)) {
                    items.append(String(lines[i].trimmingCharacters(in: .whitespaces).dropFirst(2)))
                    i += 1
                }
                blocks.append(.bulletList(items: items))
                continue
            }

            if let (_, rest) = numberedPrefix(trimmed) {
                flushParagraph(&paragraphBuffer)
                var items: [String] = [rest]
                i += 1
                while i < lines.count, let (_, r) = numberedPrefix(lines[i].trimmingCharacters(in: .whitespaces)) {
                    items.append(r)
                    i += 1
                }
                blocks.append(.numberedList(items: items))
                continue
            }

            if trimmed.isEmpty {
                flushParagraph(&paragraphBuffer)
                i += 1
                continue
            }

            paragraphBuffer.append(line)
            i += 1
        }
        flushParagraph(&paragraphBuffer)
        return blocks
    }

    private static func headingLevel(_ line: String) -> Int? {
        guard line.hasPrefix("#") else { return nil }
        let level = line.prefix(while: { $0 == "#" }).count
        guard level <= 6, line.count > level, line[line.index(line.startIndex, offsetBy: level)] == " " else { return nil }
        return level
    }

    private static func isBullet(_ line: String) -> Bool {
        (line.hasPrefix("- ") || line.hasPrefix("* ") || line.hasPrefix("+ "))
    }

    private static func numberedPrefix(_ line: String) -> (Int, String)? {
        guard let dot = line.firstIndex(where: { $0 == "." }) else { return nil }
        let numPart = line[line.startIndex..<dot]
        guard !numPart.isEmpty, numPart.allSatisfy(\.isNumber), let n = Int(numPart) else { return nil }
        let afterDot = line.index(after: dot)
        guard afterDot < line.endIndex, line[afterDot] == " " else { return nil }
        return (n, String(line[line.index(after: afterDot)...]))
    }
}

// MARK: - Block rendering

private struct BlockView: View {
    let block: MarkdownBlock

    var body: some View {
        switch block {
        case .heading(let level, let text):
            InlineRichText(text)
                .font(headingFont(level))
                .foregroundStyle(GeoTheme.ink)

        case .paragraph(let text):
            InlineRichText(text)
                .font(GeoTheme.ui(13.5))
                .foregroundStyle(GeoTheme.ink)

        case .bulletList(let items):
            VStack(alignment: .leading, spacing: 5) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("•").foregroundStyle(GeoTheme.accent).font(GeoTheme.ui(13.5, .bold))
                        InlineRichText(item).font(GeoTheme.ui(13.5)).foregroundStyle(GeoTheme.ink)
                    }
                }
            }

        case .numberedList(let items):
            VStack(alignment: .leading, spacing: 5) {
                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("\(i + 1).").foregroundStyle(GeoTheme.accent).font(GeoTheme.ui(13.5, .semibold))
                            .frame(minWidth: 18, alignment: .trailing)
                        InlineRichText(item).font(GeoTheme.ui(13.5)).foregroundStyle(GeoTheme.ink)
                    }
                }
            }

        case .blockquote(let text):
            HStack(spacing: 10) {
                Rectangle().fill(GeoTheme.border).frame(width: 3)
                InlineRichText(text).font(GeoTheme.ui(13)).foregroundStyle(GeoTheme.inkSecondary)
                    .italic()
            }

        case .codeBlock(let language, let text):
            VStack(alignment: .leading, spacing: 0) {
                if !language.isEmpty {
                    Text(language)
                        .font(GeoTheme.mono(10, .medium)).foregroundStyle(GeoTheme.inkTertiary)
                        .padding(.horizontal, 10).padding(.top, 7)
                }
                // A horizontal ScrollView sizes itself to its content's width
                // unless something bounds it — without maxWidth here, a long
                // line just grows the whole bubble instead of scrolling.
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(text)
                        .font(GeoTheme.mono(11.5))
                        .foregroundStyle(GeoTheme.ink)
                        .textSelection(.enabled)
                        .padding(10)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 9))
            .overlay(RoundedRectangle(cornerRadius: 9).stroke(GeoTheme.border, lineWidth: 1))

        case .mathBlock(let latex):
            HStack {
                Spacer(minLength: 0)
                MathView(latex: latex, displayMode: true)
                Spacer(minLength: 0)
            }
            .padding(.vertical, 4)

        case .rule:
            Rectangle().fill(GeoTheme.border).frame(height: 1)
        }
    }

    private func headingFont(_ level: Int) -> Font {
        switch level {
        case 1: return GeoTheme.ui(19, .bold)
        case 2: return GeoTheme.ui(16.5, .bold)
        default: return GeoTheme.ui(14.5, .semibold)
        }
    }
}

// MARK: - Inline rendering (text + `$…$` math, flowed together)

private struct InlineRichText: View {
    let source: String
    var font: Font = GeoTheme.ui(13.5)
    var color: Color = GeoTheme.ink
    private var italicized = false

    init(_ source: String) { self.source = source }

    func font(_ font: Font) -> InlineRichText {
        var copy = self; copy.font = font; return copy
    }
    func foregroundStyle(_ color: Color) -> InlineRichText {
        var copy = self; copy.color = color; return copy
    }
    func italic() -> InlineRichText {
        var copy = self; copy.italicized = true; return copy
    }

    var body: some View {
        // Text handed an unconstrained proposal (which is what a custom Layout's
        // subviews get) reports its full single-line width, not a wrapped one —
        // so a whole paragraph as one chip in a flow layout doesn't wrap, it
        // just runs off the edge of the screen. Word-level chips keep each one
        // small enough that this never bites; the plain (no-math) case skips
        // the flow layout entirely and gets SwiftUI's normal Text wrapping.
        if !hasMath {
            Text(styled(source))
                .font(italicized ? font.italic() : font)
                .foregroundStyle(color)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            FlowLayout(spacing: 4) {
                ForEach(Array(segments.enumerated()), id: \.offset) { _, segment in
                    switch segment {
                    case .text(let attributed):
                        Text(attributed)
                            .font(italicized ? font.italic() : font)
                            .foregroundStyle(color)
                            .textSelection(.enabled)
                            .fixedSize()
                    case .math(let latex):
                        MathView(latex: latex)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var hasMath: Bool {
        guard let firstDollar = source.firstIndex(of: "$") else { return false }
        let rest = source[source.index(after: firstDollar)...]
        return rest.contains("$")
    }

    private enum Segment {
        case text(AttributedString)
        case math(String)
    }

    /// Word-level so each text chip reports a small, accurate width to the
    /// flow layout instead of one unwrapped paragraph-wide blob.
    private var segments: [Segment] {
        var out: [Segment] = []
        var plain = ""
        let chars = Array(source)
        var i = 0
        func flushPlain() {
            let trimmed = plain.trimmingCharacters(in: .whitespaces)
            if !trimmed.isEmpty {
                for word in trimmed.split(separator: " ") {
                    out.append(.text(styled(String(word))))
                }
            }
            plain = ""
        }
        while i < chars.count {
            if chars[i] == "$", i + 1 < chars.count, chars[i + 1] != "$" {
                if let close = chars[(i + 1)...].firstIndex(of: "$") {
                    flushPlain()
                    out.append(.math(String(chars[(i + 1)..<close])))
                    i = close + 1
                    continue
                }
            }
            plain.append(chars[i])
            i += 1
        }
        flushPlain()
        return out
    }

    private func styled(_ text: String) -> AttributedString {
        (try? AttributedString(markdown: text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(text)
    }
}

// MARK: - Flow layout

/// Left-to-right layout that wraps to a new line when a subview would
/// overflow the available width — what lets inline math sit in the middle of
/// a sentence instead of forcing a line break before and after it.
private struct FlowLayout: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, lineHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width {
                x = 0
                y += lineHeight + spacing
                lineHeight = 0
            }
            x += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
        return CGSize(width: width.isFinite ? width : x, height: y + lineHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x: CGFloat = bounds.minX, y: CGFloat = bounds.minY, lineHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > bounds.minX, x + size.width > bounds.maxX {
                x = bounds.minX
                y += lineHeight + spacing
                lineHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), anchor: .topLeading, proposal: ProposedViewSize(size))
            x += size.width + spacing
            lineHeight = max(lineHeight, size.height)
        }
    }
}
