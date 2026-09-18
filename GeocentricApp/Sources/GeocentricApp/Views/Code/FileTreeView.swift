import SwiftUI

private let excludedNames: Set<String> = [
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".geocentric",
    ".build", "DerivedData", ".DS_Store", "dist", "build", ".egg-info",
]

final class FileNode: Identifiable, Hashable {
    let id: String
    let url: URL
    let isDirectory: Bool

    private var _children: [FileNode]?

    init(url: URL, isDirectory: Bool) {
        self.url = url
        self.isDirectory = isDirectory
        self.id = url.path
    }

    var name: String { url.lastPathComponent }

    /// nil for files (leaf), lazily-scanned array for directories.
    var children: [FileNode]? {
        guard isDirectory else { return nil }
        if let cached = _children { return cached }
        let fm = FileManager.default
        guard let entries = try? fm.contentsOfDirectory(
            at: url, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]
        ) else {
            _children = []
            return []
        }
        let nodes = entries
            .filter { !excludedNames.contains($0.lastPathComponent) && !$0.lastPathComponent.hasSuffix(".egg-info") }
            .sorted { a, b in
                let aDir = (try? a.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
                let bDir = (try? b.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
                if aDir != bDir { return aDir }
                return a.lastPathComponent.localizedStandardCompare(b.lastPathComponent) == .orderedAscending
            }
            .map { url -> FileNode in
                let isDir = (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
                return FileNode(url: url, isDirectory: isDir)
            }
        _children = nodes
        return nodes
    }

    static func == (lhs: FileNode, rhs: FileNode) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct FileTreeView: View {
    let rootPath: String
    let changedPaths: Set<String>
    let onSelect: (URL) -> Void

    @State private var root: FileNode?

    var body: some View {
        Group {
            if let root {
                List {
                    OutlineGroup(root.children ?? [], children: \.children) { node in
                        rowLabel(node)
                            .onTapGesture {
                                if !node.isDirectory { onSelect(node.url) }
                            }
                    }
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
            } else {
                Text("No project open")
                    .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkTertiary).padding()
            }
        }
        .background(GeoTheme.canvasWarm)
        .onAppear { reload() }
        .onChange(of: rootPath) { reload() }
    }

    private func reload() {
        let url = URL(fileURLWithPath: rootPath)
        root = FileNode(url: url, isDirectory: true)
    }

    private func rowLabel(_ node: FileNode) -> some View {
        let changed = changedPaths.contains(node.url.path)
        return HStack(spacing: 5) {
            Image(systemName: node.isDirectory ? "folder.fill" : "doc")
                .font(.system(size: 10))
                .foregroundStyle(node.isDirectory ? GeoTheme.inkTertiary : GeoTheme.inkSecondary)
            Text(node.name)
                .font(GeoTheme.ui(11.5, changed ? .medium : .regular))
                .foregroundStyle(changed ? GeoTheme.accent : GeoTheme.ink)
            if changed {
                Circle().fill(GeoTheme.accent).frame(width: 4, height: 4)
            }
        }
    }
}
