import SwiftUI
import AppKit
import PDFKit

struct WorkSurfaceView: View {
    @ObservedObject var state: AppState
    @ObservedObject var store: LocalWorkspaceStore
    @Binding var module: WorkModule
    @Binding var draft: String
    @Binding var focusMode: Bool
    @State private var assistantVisible = true

    var body: some View {
        VStack(spacing: 0) {
            WorkToolbar(module: $module, focusMode: $focusMode, assistantVisible: $assistantVisible)
            if focusMode {
                workTool
            } else {
                HSplitView {
                    workTool
                    if assistantVisible {
                        WorkAssistantPane(state: state, draft: $draft)
                            .frame(minWidth: 280, idealWidth: 330, maxWidth: 420)
                            .transition(.move(edge: .trailing).combined(with: .opacity))
                    }
                }
            }
        }
        .background(GeoTheme.canvas)
        .animation(.spring(response: 0.3, dampingFraction: 0.85), value: assistantVisible)
    }

    @ViewBuilder
    private var workTool: some View {
        switch module {
        case .documents: DocumentDesk(store: store)
        case .markdown: MarkdownDesk(store: store)
        case .sheets: SheetDesk(store: store)
        case .presentations: PresentationDesk(store: store)
        case .whiteboard: WhiteboardDesk(store: store)
        case .notes: NotesDesk(store: store)
        case .tasks: TasksDesk(store: store)
        case .calendar: CalendarDesk(store: store)
        case .board: BoardDesk(store: store)
        case .knowledge: KnowledgeDesk(store: store)
        case .files: WorkFilesDesk(state: state)
        case .pdf: PDFDesk()
        case .csv: CSVDesk()
        case .images: ImageAnnotatorDesk(store: store)
        case .diagrams: DiagramDesk(store: store)
        case .database: DatabaseDesk()
        }
    }
}

private struct WorkToolbar: View {
    @Binding var module: WorkModule
    @Binding var focusMode: Bool
    @Binding var assistantVisible: Bool

    var body: some View {
        ViewThatFits(in: .horizontal) {
            content(showSubtitle: true)
            content(showSubtitle: false)
        }
        .frame(height: 42)
        .background(GeoTheme.canvasWarm)
        .overlay(alignment: .bottom) { Rectangle().fill(GeoTheme.border).frame(height: 1) }
    }

    private func content(showSubtitle: Bool) -> some View {
        HStack(spacing: 10) {
            Label(module.title, systemImage: module.icon)
                .font(GeoTheme.ui(12, .semibold))
                .foregroundStyle(GeoTheme.ink)
                .lineLimit(1)
                .layoutPriority(1)
            if showSubtitle {
                Text("Local workspace")
                    .font(GeoTheme.ui(10.5))
                    .foregroundStyle(GeoTheme.inkTertiary)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Menu {
                ForEach(WorkModule.allCases) { item in
                    Button { module = item } label: { Label(item.title, systemImage: item.icon) }
                }
            } label: {
                Label("Tools", systemImage: "square.grid.2x2")
                    .font(GeoTheme.ui(11.5, .medium))
                    .foregroundStyle(GeoTheme.inkSecondary)
                    .padding(.horizontal, 9).padding(.vertical, 6)
                    .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: 7))
                    .overlay(RoundedRectangle(cornerRadius: 7).stroke(GeoTheme.border, lineWidth: 1))
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()

            Button {
                withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) { assistantVisible.toggle() }
            } label: {
                Image(systemName: "sidebar.right").frame(width: 27, height: 27)
            }
            .buttonStyle(.plain)
            .foregroundStyle(assistantVisible ? GeoTheme.ink : GeoTheme.inkSecondary)
            .help(assistantVisible ? "Hide Geo" : "Show Geo")

            Button { withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) { focusMode.toggle() } } label: {
                Image(systemName: focusMode ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                    .frame(width: 27, height: 27)
            }
            .buttonStyle(.plain).foregroundStyle(GeoTheme.inkSecondary)
            .help(focusMode ? "Leave focus mode" : "Focus this tool")
        }
        .padding(.horizontal, 16)
        .frame(height: 42)
    }
}

private struct WorkAssistantPane: View {
    @ObservedObject var state: AppState
    @Binding var draft: String

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                if state.mascotVisible && !state.mascotFloating {
                    GeoSpriteView(state: state.mascotState, height: 26)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text("Geo · Cowork").font(GeoTheme.ui(12, .semibold))
                    Text("Work companion").font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Spacer()
            }
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background(GeoTheme.canvasWarm)
            .overlay(alignment: .bottom) { Rectangle().fill(GeoTheme.border).frame(height: 1) }

            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if state.timeline.isEmpty {
                        Text("A quiet place to get real work done.")
                            .font(GeoTheme.serif(20)).foregroundStyle(GeoTheme.ink)
                        Text("Ask Geo to structure a plan, draft an outline, turn notes into tasks, or help navigate your local work.")
                            .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    } else {
                        ForEach(state.timeline.suffix(28)) { entry in
                            if entry.kind == .toolCall, let record = entry.toolCall { ToolCallCardView(record: record) }
                            else { MessageBubbleView(entry: entry) }
                        }
                    }
                    if state.busy && !(state.timeline.last?.kind == .assistantMessage && state.timeline.last?.isStreaming == true) {
                        ThinkingRow(text: state.thinkingHint.isEmpty ? state.agentActivity.label : state.thinkingHint)
                    }
                }
                .padding(12)
            }

            ComposerCard(
                state: state,
                text: $draft,
                placeholder: "Ask Geo to help with your work",
                showTypingCompanion: true
            )
            .padding(10)
        }
        .background(GeoTheme.canvasWarm)
    }
}

// MARK: - Documents and notes

private struct DocumentDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var selectedID: UUID?

    private var selectedIndex: Int? {
        guard let selectedID else { return store.documents.indices.first }
        return store.documents.firstIndex { $0.id == selectedID }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    Text("DOCUMENTS").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                    Spacer()
                    Button {
                        selectedID = store.addDocument()
                    } label: { Image(systemName: "plus") }
                    .buttonStyle(.plain).foregroundStyle(GeoTheme.accent).help("New document")
                }
                .padding(12)
                List(selection: $selectedID) {
                    ForEach(store.documents) { document in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(document.title.isEmpty ? "Untitled document" : document.title).lineLimit(1)
                            Text(document.modifiedAt, style: .relative)
                                .font(GeoTheme.ui(9.5)).foregroundStyle(GeoTheme.inkTertiary)
                        }
                        .tag(document.id)
                    }
                }
                .listStyle(.sidebar)
            }
            .frame(minWidth: 190, idealWidth: 225, maxWidth: 300)
            .background(.regularMaterial)

            if let index = selectedIndex {
                documentEditor(index: index)
            } else {
                WorkEmptyState(icon: "doc.richtext", title: "Create your first document", detail: "Rich text, native undo, and local storage are ready when you are.") {
                    selectedID = store.addDocument()
                }
            }
        }
    }

    private func documentEditor(index: Int) -> some View {
        VStack(spacing: 0) {
            TextField("Document title", text: $store.documents[index].title)
                .font(GeoTheme.serif(23))
                .textFieldStyle(.plain)
                .padding(.horizontal, 20).padding(.vertical, 14)
                .onChange(of: store.documents[index].title) { _, _ in store.documents[index].modifiedAt = .now }
            RichTextFormatBar()
            RichTextEditor(rtfData: $store.documents[index].rtfData, plainText: $store.documents[index].plainText)
                .onChange(of: store.documents[index].plainText) { _, _ in store.documents[index].modifiedAt = .now }
        }
        .background(GeoTheme.card)
    }
}

private struct MarkdownDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var selectedID: UUID?

    private var selectedIndex: Int? {
        guard let selectedID else { return store.documents.indices.first }
        return store.documents.firstIndex { $0.id == selectedID }
    }

    var body: some View {
        if let index = selectedIndex {
            HSplitView {
                VStack(spacing: 0) {
                    Text("MARKDOWN").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(12)
                    List(selection: $selectedID) {
                        ForEach(store.documents) { document in Text(document.title).tag(document.id) }
                    }
                    .listStyle(.sidebar)
                }
                .frame(minWidth: 170, idealWidth: 205, maxWidth: 270)
                VStack(spacing: 0) {
                    HStack {
                        Text("Source").font(GeoTheme.ui(11, .semibold))
                        Spacer()
                        Text("Preview").font(GeoTheme.ui(11, .semibold))
                    }
                    .padding(.horizontal, 14).padding(.vertical, 9)
                    .background(GeoTheme.canvasWarm)
                    HSplitView {
                        TextEditor(text: $store.documents[index].plainText)
                            .font(GeoTheme.mono(12.5))
                            .scrollContentBackground(.hidden)
                            .padding(10)
                            .background(GeoTheme.card)
                        MarkdownPreview(text: store.documents[index].plainText)
                            .frame(minWidth: 260)
                    }
                }
            }
        } else {
            WorkEmptyState(icon: "text.document", title: "No markdown documents", detail: "Create a document first, then edit it as Markdown.") { _ = store.addDocument() }
        }
    }
}

private struct MarkdownPreview: View {
    let text: String
    var body: some View {
        ScrollView {
            Group {
                if let rendered = try? AttributedString(markdown: text, options: .init(interpretedSyntax: .full)) {
                    Text(rendered)
                } else {
                    Text(text)
                }
            }
            .font(GeoTheme.ui(13))
            .foregroundStyle(GeoTheme.ink)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(20)
        }
        .background(GeoTheme.canvasWarm)
    }
}

private struct NotesDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var selectedID: UUID?

    private var selectedIndex: Int? {
        guard let selectedID else { return store.notes.indices.first }
        return store.notes.firstIndex { $0.id == selectedID }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    Text("NOTES").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                    Spacer()
                    Button { selectedID = store.addNote() } label: { Image(systemName: "plus") }
                        .buttonStyle(.plain).foregroundStyle(GeoTheme.accent)
                }.padding(12)
                List(selection: $selectedID) {
                    ForEach(store.notes) { note in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(note.title.isEmpty ? "Untitled note" : note.title).lineLimit(1)
                            Text(note.body).font(GeoTheme.ui(9.5)).foregroundStyle(GeoTheme.inkTertiary).lineLimit(1)
                        }.tag(note.id)
                    }
                }.listStyle(.sidebar)
            }.frame(minWidth: 190, idealWidth: 225, maxWidth: 300)
            if let index = selectedIndex {
                VStack(spacing: 0) {
                    TextField("Title", text: $store.notes[index].title)
                        .font(GeoTheme.serif(23)).textFieldStyle(.plain).padding(20)
                    Divider().overlay(GeoTheme.border)
                    TextEditor(text: $store.notes[index].body)
                        .font(GeoTheme.ui(14)).scrollContentBackground(.hidden).padding(14)
                        .onChange(of: store.notes[index].body) { _, _ in store.notes[index].updatedAt = .now }
                }.background(GeoTheme.card)
            }
        }
    }
}

// MARK: - Data and project tools

private struct SheetDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var selectedID: UUID?

    private var selectedIndex: Int? {
        guard let selectedID else { return store.sheets.indices.first }
        return store.sheets.firstIndex { $0.id == selectedID }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    Text("SHEETS").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                    Spacer()
                    Button { selectedID = store.addSheet() } label: { Image(systemName: "plus") }
                        .buttonStyle(.plain).foregroundStyle(GeoTheme.accent)
                }.padding(12)
                List(selection: $selectedID) { ForEach(store.sheets) { sheet in Text(sheet.title).tag(sheet.id) } }
                    .listStyle(.sidebar)
            }.frame(minWidth: 180, idealWidth: 210, maxWidth: 280)
            if let index = selectedIndex {
                SheetGrid(sheet: $store.sheets[index])
            } else {
                WorkEmptyState(icon: "tablecells", title: "Create a sheet", detail: "A small local spreadsheet for plans, trackers, and CSV-shaped work.") { selectedID = store.addSheet() }
            }
        }
    }
}

private struct SheetGrid: View {
    @Binding var sheet: WorkSheet

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                TextField("Sheet title", text: $sheet.title).font(GeoTheme.serif(21)).textFieldStyle(.plain)
                Spacer()
                Button { addRow() } label: { Label("Row", systemImage: "plus") }.buttonStyle(WorkActionButton(subtle: true))
                Button { addColumn() } label: { Label("Column", systemImage: "plus") }.buttonStyle(WorkActionButton(subtle: true))
            }.padding(14).background(GeoTheme.canvasWarm)
            Divider().overlay(GeoTheme.border)
            ScrollView([.horizontal, .vertical]) {
                VStack(spacing: 0) {
                    ForEach(sheet.cells.indices, id: \.self) { row in
                        HStack(spacing: 0) {
                            Text("\(row + 1)").font(GeoTheme.mono(10)).foregroundStyle(GeoTheme.inkTertiary)
                                .frame(width: 34).frame(maxHeight: .infinity).background(GeoTheme.sunken)
                            ForEach(sheet.cells[row].indices, id: \.self) { column in
                                TextField("", text: $sheet.cells[row][column])
                                    .textFieldStyle(.plain).font(GeoTheme.ui(12))
                                    .frame(width: 150, height: 31, alignment: .leading)
                                    .padding(.horizontal, 7)
                                    .overlay(Rectangle().stroke(GeoTheme.border, lineWidth: 0.5))
                            }
                        }
                    }
                }
                .padding(14)
            }
            .background(GeoTheme.card)
        }
    }

    private func addRow() {
        sheet.cells.append(Array(repeating: "", count: max(1, sheet.cells.first?.count ?? 1)))
    }

    private func addColumn() {
        if sheet.cells.isEmpty { sheet.cells = [[""]] }
        for index in sheet.cells.indices { sheet.cells[index].append("") }
    }
}

private struct TasksDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var newTask = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Tasks").font(GeoTheme.serif(28))
                    Text("A calm local list for the work that matters next.").font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkSecondary)
                }
                Spacer()
                Text("\(store.tasks.filter(\.complete).count)/\(store.tasks.count) complete")
                    .font(GeoTheme.ui(11.5, .medium)).foregroundStyle(GeoTheme.inkSecondary)
            }
            .padding(20)
            Divider().overlay(GeoTheme.border)
            HStack(spacing: 8) {
                TextField("Add a task", text: $newTask)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { addTask() }
                Button("Add", action: addTask).buttonStyle(WorkActionButton())
            }.padding(14)
            List {
                ForEach($store.tasks) { $task in
                    HStack(spacing: 10) {
                        Button { task.complete.toggle() } label: {
                            Image(systemName: task.complete ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(task.complete ? GeoTheme.success : GeoTheme.inkTertiary)
                        }.buttonStyle(.plain)
                        TextField("Task", text: $task.title)
                            .strikethrough(task.complete).foregroundStyle(task.complete ? GeoTheme.inkTertiary : GeoTheme.ink)
                        Spacer()
                        Text(task.project).font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                    }.padding(.vertical, 4)
                }.onDelete { store.tasks.remove(atOffsets: $0) }
            }.listStyle(.inset)
        }
        .background(GeoTheme.card)
    }

    private func addTask() { store.addTask(title: newTask); newTask = "" }
}

private struct BoardDesk: View {
    @ObservedObject var store: LocalWorkspaceStore

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Project board").font(GeoTheme.serif(28))
                    Text("Move local work from idea to done.").font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkSecondary)
                }
                Spacer()
            }.padding(20)
            Divider().overlay(GeoTheme.border)
            HStack(alignment: .top, spacing: 12) {
                ForEach(BoardColumn.allCases) { column in
                    BoardColumnView(store: store, column: column)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .background(GeoTheme.canvas)
    }
}

private struct BoardColumnView: View {
    @ObservedObject var store: LocalWorkspaceStore
    let column: BoardColumn

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(column.rawValue).font(GeoTheme.ui(12, .semibold))
                Spacer()
                Text("\(store.boardCards.filter { $0.column == column }.count)").font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
            }
            ForEach(store.boardCards.filter { $0.column == column }) { card in
                VStack(alignment: .leading, spacing: 7) {
                    TextField("Task", text: binding(for: card, keyPath: \.title))
                        .font(GeoTheme.ui(12, .medium)).textFieldStyle(.plain)
                    HStack {
                        Button { store.move(card, direction: -1) } label: { Image(systemName: "arrow.left") }
                            .disabled(column == .inbox)
                        Spacer()
                        Button { store.move(card, direction: 1) } label: { Image(systemName: "arrow.right") }
                            .disabled(column == .done)
                    }.font(.system(size: 10)).foregroundStyle(GeoTheme.inkTertiary).buttonStyle(.plain)
                }
                .padding(10).background(GeoTheme.card, in: RoundedRectangle(cornerRadius: 9))
                .overlay(RoundedRectangle(cornerRadius: 9).stroke(GeoTheme.border, lineWidth: 1))
            }
            Button { store.addBoardCard(to: column) } label: { Label("Add", systemImage: "plus") }
                .font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkSecondary).buttonStyle(.plain)
        }
        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
        .background(GeoTheme.sunken.opacity(0.65), in: RoundedRectangle(cornerRadius: 11))
    }

    private func binding(for card: BoardCard, keyPath: WritableKeyPath<BoardCard, String>) -> Binding<String> {
        Binding(get: { store.boardCards.first(where: { $0.id == card.id })?[keyPath: keyPath] ?? "" }, set: { value in
            if let index = store.boardCards.firstIndex(where: { $0.id == card.id }) { store.boardCards[index][keyPath: keyPath] = value }
        })
    }
}
