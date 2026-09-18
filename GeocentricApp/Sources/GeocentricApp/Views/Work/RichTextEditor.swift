import SwiftUI
import AppKit

/// Thin AppKit bridge for the one place SwiftUI's `TextEditor` cannot deliver:
/// a real local rich-text document with native text services, undo, selection,
/// copy/paste, and standard formatting commands. SwiftUI still owns the data.
struct RichTextEditor: NSViewRepresentable {
    @Binding var rtfData: Data
    @Binding var plainText: String

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        scroll.autohidesScrollers = true

        let textView = NSTextView()
        textView.isRichText = true
        textView.allowsUndo = true
        textView.usesRuler = true
        textView.isRulerVisible = false
        textView.font = NSFont.systemFont(ofSize: 14)
        textView.textColor = NSColor.labelColor
        textView.backgroundColor = .clear
        textView.textContainerInset = NSSize(width: 18, height: 18)
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.delegate = context.coordinator
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainer?.widthTracksTextView = true

        if !rtfData.isEmpty, let attributed = try? NSAttributedString(
            data: rtfData,
            options: [.documentType: NSAttributedString.DocumentType.rtf],
            documentAttributes: nil
        ) {
            textView.textStorage?.setAttributedString(attributed)
        } else {
            textView.string = plainText
        }

        context.coordinator.textView = textView
        scroll.documentView = textView
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard !context.coordinator.isUpdating, let textView = context.coordinator.textView else { return }
        let isFocused = textView.window?.firstResponder === textView
        guard textView.string != plainText, !isFocused else { return }
        textView.string = plainText
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: RichTextEditor
        weak var textView: NSTextView?
        var isUpdating = false

        init(_ parent: RichTextEditor) { self.parent = parent }

        func textDidChange(_ notification: Notification) {
            guard let textView else { return }
            isUpdating = true
            parent.plainText = textView.string
            parent.rtfData = textView.rtf(from: NSRange(location: 0, length: textView.string.utf16.count)) ?? Data()
            isUpdating = false
        }
    }
}

struct RichTextFormatBar: View {
    var body: some View {
        HStack(spacing: 3) {
            formatButton("bold", trait: .boldFontMask, label: "Bold")
            formatButton("italic", trait: .italicFontMask, label: "Italic")
            formatButton("underline", trait: nil, label: "Underline")
            Divider().frame(height: 16)
            Button {
                if let textView = NSApp.keyWindow?.firstResponder as? NSTextView {
                    textView.insertText("• ", replacementRange: textView.selectedRange())
                }
            } label: {
                Image(systemName: "list.bullet").frame(width: 24, height: 23)
            }
            .buttonStyle(.plain).foregroundStyle(GeoTheme.inkSecondary).help("Insert bullet")
        }
        .padding(.horizontal, 9).padding(.vertical, 6)
        .background(GeoTheme.canvasWarm)
        .overlay(alignment: .bottom) { Rectangle().fill(GeoTheme.border).frame(height: 1) }
    }

    private func formatButton(_ icon: String, trait: NSFontTraitMask?, label: String) -> some View {
        Button {
            guard let textView = NSApp.keyWindow?.firstResponder as? NSTextView else { return }
            let range = textView.selectedRange()
            if let trait {
                textView.textStorage?.beginEditing()
                textView.textStorage?.enumerateAttribute(.font, in: range, options: []) { value, subrange, _ in
                    let font = (value as? NSFont) ?? NSFont.systemFont(ofSize: 14)
                    let converted = NSFontManager.shared.convert(font, toHaveTrait: trait)
                    textView.textStorage?.addAttribute(.font, value: converted, range: subrange)
                }
                textView.textStorage?.endEditing()
            } else {
                textView.textStorage?.beginEditing()
                textView.textStorage?.addAttribute(.underlineStyle, value: NSUnderlineStyle.single.rawValue, range: range)
                textView.textStorage?.endEditing()
            }
        } label: {
            Image(systemName: icon).frame(width: 24, height: 23)
        }
        .buttonStyle(.plain)
        .foregroundStyle(GeoTheme.inkSecondary)
        .help(label)
    }
}
