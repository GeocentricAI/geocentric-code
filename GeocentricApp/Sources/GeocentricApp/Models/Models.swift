import Foundation

enum EntryKind: Equatable {
    case userMessage
    case assistantMessage
    case toolCall
    case planProposal
    case commandOutput
    case note
}

enum NoteStyle {
    case info, warn, error, success
}

final class ToolCallRecord: ObservableObject, Identifiable {
    let id: String
    let name: String
    let argsText: String
    let danger: String
    /// The file/command a transcript row can name inline, e.g. "Read app.py"
    /// instead of "Read tool" — derived from whichever argument actually
    /// identifies the target (path, pattern, or command), not guessed.
    let pathHint: String
    @Published var status: Status = .running
    @Published var outputText: String = ""
    @Published var diffText: String?

    enum Status { case running, ok, failed }

    init(id: String, name: String, argsText: String, danger: String = "low", pathHint: String = "") {
        self.id = id
        self.name = name
        self.argsText = argsText
        self.danger = danger
        self.pathHint = pathHint
    }
}

final class PlanProposal: ObservableObject, Identifiable {
    let id = UUID().uuidString
    let raw: String
    let goal: String
    let files: [String]
    let steps: [String]
    let risks: String
    let verification: String
    let structured: Bool
    @Published var resolved: Bool = false

    init(raw: String, goal: String, files: [String], steps: [String], risks: String, verification: String, structured: Bool) {
        self.raw = raw
        self.goal = goal
        self.files = files
        self.steps = steps
        self.risks = risks
        self.verification = verification
        self.structured = structured
    }
}

struct ApprovalRequest: Identifiable {
    let id: String
    let tool: String
    let argsText: String
    let danger: String
    let reasons: [String]
}

struct QuestionOption: Identifiable {
    let id = UUID()
    let label: String
    let description: String
}

struct QuestionRequest: Identifiable {
    let id = UUID()
    let question: String
    let options: [QuestionOption]
    let multiSelect: Bool
}

final class TimelineEntry: ObservableObject, Identifiable {
    let id: String
    let kind: EntryKind
    let timestamp = Date()
    @Published var text: String = ""
    @Published var thinkingText: String = ""
    @Published var isStreaming: Bool = false
    @Published var toolCall: ToolCallRecord?
    @Published var plan: PlanProposal?
    @Published var style: NoteStyle = .info

    init(id: String = UUID().uuidString, kind: EntryKind) {
        self.id = id
        self.kind = kind
    }
}

struct ClusterPeer: Identifiable, Equatable {
    let id: String
    let name: String
    let address: String
    var paired: Bool = false
}

enum ClusterMode: String {
    case cluster
    case orchestration

    var title: String {
        switch self {
        case .cluster: return "Cluster"
        case .orchestration: return "Orchestration"
        }
    }
    var subtitle: String {
        switch self {
        case .cluster: return "Both Macs run one bigger model together (needs exo installed)"
        case .orchestration: return "Each Mac runs its own model; they split tasks and talk to each other"
        }
    }
}

struct SessionSummary: Identifiable {
    let id: String
    let when: String
    let age: String
    let turns: Int
    let model: String
    let title: String
}

struct ModelInfo: Identifiable, Hashable {
    var id: String { name }
    let name: String
    let sizeBytes: Int
    let supportsTools: Bool
    let supportsThinking: Bool
}

struct ToolInfo: Identifiable {
    var id: String { name }
    let name: String
    let description: String
    let danger: String
    let mutating: Bool
    let group: String
}

struct BackgroundJob: Identifiable {
    let id: String
}

enum MascotState: Equatable {
    case idle          // standing, periodic blink
    case pondering     // deciding the next step, before any tool or text lands
    case active        // seated, typing loop with code appearing on screen
    case waiting       // pending approval/question — looks side to side for you
    case celebrating   // a turn just finished cleanly — one quick happy hop
    case worried       // an error just landed — one quick concerned shake
}

enum WorkspaceMode: String, CaseIterable, Identifiable {
    case chat
    case code
    case work

    var id: String { rawValue }

    /// Cowork is fully built but hidden from navigation for now — Chat and
    /// Code are the app's focus. The mode itself isn't deleted, so restoring
    /// it later is a one-line change here rather than rebuilding the surface.
    static var visibleCases: [WorkspaceMode] { [.chat, .code] }

    var title: String { rawValue.capitalized }

    var subtitle: String {
        switch self {
        case .chat: return "Conversation"
        case .code: return "Local coding agent"
        case .work: return "Cowork workspace"
        }
    }

    var systemImage: String {
        switch self {
        case .chat: return "bubble.left.and.bubble.right"
        case .code: return "chevron.left.forwardslash.chevron.right"
        case .work: return "square.grid.2x2"
        }
    }
}

enum AgentActivity: Equatable {
    case idle
    case preparing
    case thinking
    case usingTool(String)
    case waitingForApproval

    var label: String {
        switch self {
        case .idle: return "Ready"
        case .preparing: return "Getting ready"
        case .thinking: return "Thinking"
        case .usingTool(let tool): return "Using \(tool)"
        case .waitingForApproval: return "Needs your approval"
        }
    }

    var mascotState: MascotState { self == .idle ? .idle : .active }
}

enum WorkModule: String, CaseIterable, Identifiable {
    case documents
    case markdown
    case sheets
    case presentations
    case whiteboard
    case notes
    case tasks
    case calendar
    case board
    case knowledge
    case files
    case pdf
    case csv
    case images
    case diagrams
    case database

    var id: String { rawValue }

    var title: String {
        switch self {
        case .documents: return "Documents"
        case .markdown: return "Markdown"
        case .sheets: return "Sheets"
        case .presentations: return "Presentations"
        case .whiteboard: return "Whiteboard"
        case .notes: return "Notes"
        case .tasks: return "Tasks"
        case .calendar: return "Calendar"
        case .board: return "Projects"
        case .knowledge: return "Knowledge"
        case .files: return "Files"
        case .pdf: return "PDF"
        case .csv: return "CSV"
        case .images: return "Images"
        case .diagrams: return "Diagrams"
        case .database: return "Database"
        }
    }

    var icon: String {
        switch self {
        case .documents: return "doc.richtext"
        case .markdown: return "text.document"
        case .sheets: return "tablecells"
        case .presentations: return "rectangle.on.rectangle.angled"
        case .whiteboard: return "pencil.and.outline"
        case .notes: return "note.text"
        case .tasks: return "checklist"
        case .calendar: return "calendar"
        case .board: return "rectangle.3.group"
        case .knowledge: return "books.vertical"
        case .files: return "folder"
        case .pdf: return "doc.fill"
        case .csv: return "list.bullet.rectangle"
        case .images: return "photo"
        case .diagrams: return "point.3.connected.trianglepath.dotted"
        case .database: return "cylinder.split.1x2"
        }
    }
}

enum ConnectionState: Equatable {
    case disconnected
    case connecting
    case ready
    case ollamaUnreachable(host: String)
    case fatal(String)
}
