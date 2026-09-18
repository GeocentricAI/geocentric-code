import Foundation

/// Reads the current branch and uncommitted diffstat for the open project by
/// shelling out to the system `git` directly — this is read-only local status,
/// not agent activity, so it doesn't need to go through the Python engine.
@MainActor
final class GitStatusProbe: ObservableObject {
    @Published var branch: String?
    @Published var insertions: Int = 0
    @Published var deletions: Int = 0
    @Published var isRepo = false

    private var lastPath = ""

    func refresh(path: String) {
        lastPath = path
        Task { [weak self] in
            guard let self else { return }
            let branch = await Self.run(["rev-parse", "--abbrev-ref", "HEAD"], in: path)
            let stat = await Self.run(["diff", "--shortstat", "HEAD"], in: path)
            guard self.lastPath == path else { return } // a newer request already superseded this one
            guard let branch, !branch.isEmpty else {
                self.isRepo = false
                self.branch = nil
                return
            }
            self.isRepo = true
            self.branch = branch
            let (ins, del) = Self.parseShortstat(stat ?? "")
            self.insertions = ins
            self.deletions = del
        }
    }

    private static func parseShortstat(_ text: String) -> (Int, Int) {
        var insertions = 0, deletions = 0
        if let range = text.range(of: #"(\d+) insertion"#, options: .regularExpression) {
            insertions = Int(text[range].filter(\.isNumber)) ?? 0
        }
        if let range = text.range(of: #"(\d+) deletion"#, options: .regularExpression) {
            deletions = Int(text[range].filter(\.isNumber)) ?? 0
        }
        return (insertions, deletions)
    }

    private static func run(_ args: [String], in directory: String) async -> String? {
        await withCheckedContinuation { continuation in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
            process.arguments = args
            process.currentDirectoryURL = URL(fileURLWithPath: directory)
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = Pipe()
            process.terminationHandler = { proc in
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let text = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
                continuation.resume(returning: proc.terminationStatus == 0 ? text : nil)
            }
            do {
                try process.run()
            } catch {
                continuation.resume(returning: nil)
            }
        }
    }
}
