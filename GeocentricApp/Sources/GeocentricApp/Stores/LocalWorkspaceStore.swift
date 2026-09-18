import Foundation
import Combine

/// Lightweight, offline persistence for Work mode. The store deliberately uses
/// a single Codable snapshot: local work remains inspectable, portable, and
/// crash-safe without adding a service/database dependency to the app shell.
@MainActor
final class LocalWorkspaceStore: ObservableObject {
    @Published var documents: [WorkDocument] { didSet { saveSoon() } }
    @Published var notes: [WorkNote] { didSet { saveSoon() } }
    @Published var tasks: [WorkTask] { didSet { saveSoon() } }
    @Published var boardCards: [BoardCard] { didSet { saveSoon() } }
    @Published var sheets: [WorkSheet] { didSet { saveSoon() } }
    @Published var slides: [WorkSlide] { didSet { saveSoon() } }
    @Published var strokes: [CanvasStroke] { didSet { saveSoon() } }
    @Published var diagramNodes: [DiagramNode] { didSet { saveSoon() } }
    @Published var diagramLinks: [DiagramLink] { didSet { saveSoon() } }
    /// Annotation boxes for images opened in the annotator, keyed by file path
    /// so re-opening the same image restores its markup.
    @Published var imageAnnotations: [String: [ImageAnnotation]] { didSet { saveSoon() } }

    private var pendingSave: DispatchWorkItem?

    private struct Snapshot: Codable {
        var documents: [WorkDocument]
        var notes: [WorkNote]
        var tasks: [WorkTask]
        var boardCards: [BoardCard]
        var sheets: [WorkSheet]
        var slides: [WorkSlide]
        var strokes: [CanvasStroke]
        var diagramNodes: [DiagramNode]
        var diagramLinks: [DiagramLink] = []
        var imageAnnotations: [String: [ImageAnnotation]] = [:]
    }

    init() {
        if let snapshot = Self.load() {
            documents = snapshot.documents
            notes = snapshot.notes
            tasks = snapshot.tasks
            boardCards = snapshot.boardCards
            sheets = snapshot.sheets
            slides = snapshot.slides
            strokes = snapshot.strokes
            diagramNodes = snapshot.diagramNodes
            diagramLinks = snapshot.diagramLinks
            imageAnnotations = snapshot.imageAnnotations
        } else {
            documents = [WorkDocument(title: "Welcome to Work", plainText: "A private local workspace for thinking, making, and organizing.")]
            notes = [WorkNote(title: "Getting started", body: "Use Work for documents, sheets, plans, notes, and local project coordination.")]
            tasks = [WorkTask(title: "Make this workspace your own", dueDate: .now, project: "Getting started")]
            boardCards = [BoardCard(title: "Explore your work tools", column: .inbox)]
            sheets = [WorkSheet(title: "New sheet", cells: [["Task", "Owner", "Status"], ["Plan a project", "Me", "In progress"], ["Share next steps", "Me", "Not started"]])]
            slides = [WorkSlide(title: "A local work canvas", body: "Build documents, data, and plans without leaving your machine.")]
            strokes = []
            diagramNodes = [DiagramNode(title: "Idea", x: 100, y: 100), DiagramNode(title: "Plan", x: 270, y: 170, colorHex: 0xD97757)]
            diagramLinks = []
            imageAnnotations = [:]
        }
    }

    func addDocument() -> UUID {
        let doc = WorkDocument(title: "Untitled document")
        documents.insert(doc, at: 0)
        return doc.id
    }

    func addNote() -> UUID {
        let note = WorkNote(title: "Untitled note", body: "")
        notes.insert(note, at: 0)
        return note.id
    }

    func addTask(title: String, project: String = "Inbox") {
        guard !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        tasks.insert(WorkTask(title: title, project: project), at: 0)
    }

    func addSheet() -> UUID {
        let sheet = WorkSheet(title: "Untitled sheet", cells: [["Column A", "Column B"], ["", ""]])
        sheets.insert(sheet, at: 0)
        return sheet.id
    }

    func addSlide() -> UUID {
        let slide = WorkSlide(title: "New slide", body: "Add your idea here.")
        slides.append(slide)
        return slide.id
    }

    func addBoardCard(to column: BoardColumn) {
        boardCards.append(BoardCard(title: "Untitled task", column: column))
    }

    func move(_ card: BoardCard, direction: Int) {
        guard let index = BoardColumn.allCases.firstIndex(of: card.column) else { return }
        let target = max(0, min(BoardColumn.allCases.count - 1, index + direction))
        guard target != index, let cardIndex = boardCards.firstIndex(of: card) else { return }
        boardCards[cardIndex].column = BoardColumn.allCases[target]
    }

    func snapshot() -> Data? {
        try? JSONEncoder().encode(Snapshot(
            documents: documents, notes: notes, tasks: tasks, boardCards: boardCards,
            sheets: sheets, slides: slides, strokes: strokes, diagramNodes: diagramNodes,
            diagramLinks: diagramLinks, imageAnnotations: imageAnnotations
        ))
    }

    private func saveSoon() {
        pendingSave?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.save() }
        pendingSave = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.45, execute: work)
    }

    private func save() {
        guard let data = snapshot() else { return }
        try? FileManager.default.createDirectory(at: Self.storageURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? data.write(to: Self.storageURL, options: .atomic)
    }

    private static func load() -> Snapshot? {
        guard let data = try? Data(contentsOf: storageURL) else { return nil }
        return try? JSONDecoder().decode(Snapshot.self, from: data)
    }

    private static var storageURL: URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return appSupport.appendingPathComponent("Geocentric", isDirectory: true).appendingPathComponent("workspace.json")
    }
}
