import SwiftUI

/// Small pill button used for the suggestion row under the composer.
struct SuggestionChip: View {
    let icon: String
    let title: String
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 11, weight: .medium))
                Text(title).font(GeoTheme.ui(12.5, .medium))
            }
            .foregroundStyle(GeoTheme.ink)
            .padding(.horizontal, 13)
            .padding(.vertical, 8)
            .background(hovering ? GeoTheme.canvasWarm : GeoTheme.card, in: Capsule())
            .overlay(Capsule().stroke(GeoTheme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
    }
}

/// Larger suggestion card with inline `code` styling, as on the Code surface.
struct SuggestionCard: View {
    let segments: [(String, Bool)]  // (text, isCode)
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            segments.reduce(Text("")) { acc, seg in
                acc + (seg.1
                    ? Text(seg.0).font(GeoTheme.mono(12)).foregroundColor(GeoTheme.accent)
                    : Text(seg.0).font(GeoTheme.ui(12.5)).foregroundColor(GeoTheme.ink))
            }
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(hovering ? GeoTheme.canvasWarm : GeoTheme.card,
                        in: RoundedRectangle(cornerRadius: GeoTheme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: GeoTheme.cardRadius).stroke(GeoTheme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
    }
}

/// Borderless icon button for toolbars and the icon rail.
struct RailIconButton: View {
    let icon: String
    var active: Bool = false
    var help: String = ""
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .regular))
                .foregroundStyle(active ? GeoTheme.ink : GeoTheme.inkSecondary)
                .frame(width: 30, height: 30)
                .background(
                    RoundedRectangle(cornerRadius: 7)
                        .fill(active ? GeoTheme.borderStrong.opacity(0.5)
                                     : (hovering ? GeoTheme.borderStrong.opacity(0.28) : .clear))
                )
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help(help)
    }
}

/// The global workspace switcher. It lives in Geocentric's own chrome rather
/// than the system toolbar so it never fights the traffic-light/titlebar area.
struct SurfaceSwitcher: View {
    @Binding var selection: WorkspaceMode

    var body: some View {
        HStack(spacing: 2) {
            ForEach(WorkspaceMode.visibleCases) { surface in
                let active = selection == surface
                Button {
                    selection = surface
                } label: {
                    Label(surface.title, systemImage: surface.systemImage)
                        .font(GeoTheme.ui(12.5, active ? .semibold : .regular))
                        .foregroundStyle(active ? GeoTheme.ink : GeoTheme.inkSecondary)
                        .labelStyle(.titleAndIcon)
                        .padding(.horizontal, 15)
                        .padding(.vertical, 5)
                        .background(
                            RoundedRectangle(cornerRadius: 7)
                                .fill(active ? GeoTheme.card : .clear)
                                .shadow(color: active ? .black.opacity(0.06) : .clear, radius: 2, y: 1)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(3)
        .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 9))
    }
}

/// Inline dropdown used for the model picker inside the composer.
struct QuietMenuLabel: View {
    let text: String
    /// When set (and `text` is empty), the label collapses to just this SF
    /// Symbol — used when the composer is too narrow for the full name.
    var icon: String? = nil

    var body: some View {
        HStack(spacing: 3) {
            if let icon, text.isEmpty {
                Image(systemName: icon).font(.system(size: 11))
                    .foregroundStyle(GeoTheme.inkSecondary)
            } else {
                Text(text).font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkSecondary)
                    .lineLimit(1).fixedSize()
            }
            Image(systemName: "chevron.down").font(.system(size: 8, weight: .semibold))
                .foregroundStyle(GeoTheme.inkTertiary)
        }
    }
}

/// The tan "Bypass permissions" pill on a coding agent's composer — toggles
/// auto-accept for mutating tool calls. Destructive commands still confirm
/// regardless of this setting (enforced on the Python side, not here).
struct PermissionsChip: View {
    let enabled: Bool
    var compact: Bool = false
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: enabled ? "checkmark.shield.fill" : "shield")
                    .font(.system(size: 10))
                if !compact {
                    Text(enabled ? "Bypassing permissions" : "Bypass permissions")
                        .font(GeoTheme.ui(11, .medium))
                        .lineLimit(1)
                        .fixedSize()
                }
            }
            .foregroundStyle(enabled ? Color(hex: 0x8A6A2F) : GeoTheme.inkSecondary)
            .padding(.horizontal, compact ? 6 : 9).padding(.vertical, 5)
            .background(
                (enabled ? Color(hex: 0xF5E3B8) : (hovering ? GeoTheme.canvasWarm : Color.clear)),
                in: Capsule()
            )
            .overlay(Capsule().stroke(enabled ? Color(hex: 0xE0C578) : GeoTheme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .fixedSize()
        .onHover { hovering = $0 }
        .help(enabled ? "Auto-accept is on — destructive commands still ask" : "Ask before every change")
    }
}
