import SwiftUI
import AppKit

/// A plain, auto-growing text field for the composer. SwiftUI's own
/// `TextEditor` wraps an NSScrollView whose scroll-indicator track paints a
/// stray vertical bar in the corner even for a single line of text; this
/// talks to NSTextView directly with both scrollers off, so there's nothing
/// left to paint but the text itself.
struct ComposerTextView: NSViewRepresentable {
    @Binding var text: String
    @Binding var contentHeight: CGFloat
    @Binding var isFocused: Bool
    var font: NSFont
    var grabFocusOnAppear: Bool = false
    var onSubmit: () -> Void

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = false
        scrollView.hasHorizontalScroller = false
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder

        let contentWidth = scrollView.contentSize.width
        let textView = NSTextView(frame: NSRect(x: 0, y: 0, width: contentWidth, height: 20))
        textView.delegate = context.coordinator
        textView.font = font
        textView.textColor = NSColor(GeoTheme.ink)
        textView.backgroundColor = .clear
        textView.drawsBackground = false
        textView.isRichText = false
        // The boilerplate an auto-growing NSTextView actually needs to track its
        // enclosing scroll view's width: without `autoresizingMask`/min/maxSize,
        // the document view keeps whatever frame it was created with forever —
        // here that would be zero-width, since SwiftUI never independently
        // resizes the *document view*, only the NSScrollView around it. Every
        // glyph would then lay out and paint into a zero-width clip: present in
        // the string, present in the color attributes, and completely invisible.
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainerInset = NSSize(width: 0, height: 2)
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(width: contentWidth, height: .greatestFiniteMagnitude)

        scrollView.documentView = textView

        if grabFocusOnAppear {
            DispatchQueue.main.async { scrollView.window?.makeFirstResponder(textView) }
        }
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }
        if textView.string != text {
            textView.string = text
        }
        context.coordinator.onSubmit = onSubmit
        if text.isEmpty {
            // Skip the layout round-trip for the common "just sent, clear it" case —
            // waiting on `usedRect` here is what let a stale, oversized height stick
            // around after rapid sends.
            if contentHeight != 20 { contentHeight = 20 }
        } else {
            DispatchQueue.main.async { context.coordinator.updateHeight(textView) }
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text, contentHeight: $contentHeight, isFocused: $isFocused, onSubmit: onSubmit)
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var text: Binding<String>
        var contentHeight: Binding<CGFloat>
        var isFocused: Binding<Bool>
        var onSubmit: () -> Void

        init(text: Binding<String>, contentHeight: Binding<CGFloat>, isFocused: Binding<Bool>, onSubmit: @escaping () -> Void) {
            self.text = text
            self.contentHeight = contentHeight
            self.isFocused = isFocused
            self.onSubmit = onSubmit
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            text.wrappedValue = textView.string
            updateHeight(textView)
        }

        func textDidBeginEditing(_ notification: Notification) {
            isFocused.wrappedValue = true
        }

        func textDidEndEditing(_ notification: Notification) {
            isFocused.wrappedValue = false
        }

        func updateHeight(_ textView: NSTextView) {
            guard let layoutManager = textView.layoutManager, let container = textView.textContainer else { return }
            layoutManager.ensureLayout(for: container)
            let used = layoutManager.usedRect(for: container).height + textView.textContainerInset.height * 2
            let clamped = max(20, used)
            if abs(contentHeight.wrappedValue - clamped) > 0.5 {
                contentHeight.wrappedValue = clamped
            }
        }

        // Return sends; Shift+Return inserts a real newline.
        func textView(_ textView: NSTextView, doCommandBy selector: Selector) -> Bool {
            guard selector == #selector(NSResponder.insertNewline(_:)) else { return false }
            guard let event = NSApp.currentEvent, event.modifierFlags.contains(.shift) else {
                onSubmit()
                return true
            }
            return false
        }
    }
}
