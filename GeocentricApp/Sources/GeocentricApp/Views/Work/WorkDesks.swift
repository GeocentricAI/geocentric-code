import SwiftUI
import AppKit
import PDFKit

// MARK: - Shared UI Components for Work Mode

struct WorkEmptyState: View {
    let icon: String
    let title: String
    let detail: String
    let actionTitle: String
    let action: () -> Void

    init(icon: String, title: String, detail: String, actionTitle: String = "Create New", action: @escaping () -> Void) {
        self.icon = icon
        self.title = title
        self.detail = detail
        self.actionTitle = actionTitle
        self.action = action
    }

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(GeoTheme.accent)
            Text(title)
                .font(GeoTheme.serif(22))
                .foregroundStyle(GeoTheme.ink)
            Text(detail)
                .font(GeoTheme.ui(13))
                .foregroundStyle(GeoTheme.inkSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 340)
            Button(action: action) {
                HStack(spacing: 6) {
                    Image(systemName: "plus")
                    Text(actionTitle)
                }
                .font(GeoTheme.ui(12, .semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(GeoTheme.accent, in: Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(GeoTheme.card)
    }
}

struct WorkActionButton: ButtonStyle {
    var subtle: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(GeoTheme.ui(11.5, .medium))
            .foregroundStyle(subtle ? GeoTheme.ink : .white)
            .padding(.horizontal, 11)
            .padding(.vertical, 6)
            .background(
                subtle ? GeoTheme.sunken : (configuration.isPressed ? GeoTheme.accent.opacity(0.85) : GeoTheme.accent),
                in: RoundedRectangle(cornerRadius: 6)
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .animation(.easeInOut(duration: 0.1), value: configuration.isPressed)
    }
}

// MARK: - Presentation Desk

struct PresentationDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var selectedID: UUID?

    private var selectedIndex: Int? {
        guard let selectedID else { return store.slides.indices.first }
        return store.slides.firstIndex { $0.id == selectedID }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    Text("SLIDES").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                    Spacer()
                    Button { selectedID = store.addSlide() } label: { Image(systemName: "plus") }
                        .buttonStyle(.plain).foregroundStyle(GeoTheme.accent)
                }.padding(12)

                List(selection: $selectedID) {
                    ForEach(Array(store.slides.enumerated()), id: \.element.id) { index, slide in
                        HStack(spacing: 8) {
                            Text("\(index + 1)")
                                .font(GeoTheme.mono(11, .semibold))
                                .foregroundStyle(GeoTheme.inkTertiary)
                                .frame(width: 18)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(slide.title.isEmpty ? "Untitled slide" : slide.title)
                                    .font(GeoTheme.ui(12, .medium)).lineLimit(1)
                                Text(slide.body).font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary).lineLimit(1)
                            }
                        }.tag(slide.id)
                    }
                }.listStyle(.sidebar)
            }
            .frame(minWidth: 200, idealWidth: 230, maxWidth: 300)

            if let index = selectedIndex {
                VStack(spacing: 0) {
                    HStack(spacing: 12) {
                        TextField("Slide Title", text: $store.slides[index].title)
                            .font(GeoTheme.serif(22)).textFieldStyle(.plain)
                        Spacer()
                    }.padding(16).background(GeoTheme.canvasWarm)
                    Divider()
                    ScrollView {
                        VStack(alignment: .leading, spacing: 16) {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(store.slides[index].title.isEmpty ? "Slide Title" : store.slides[index].title)
                                    .font(GeoTheme.serif(32))
                                    .foregroundStyle(GeoTheme.ink)
                                Divider()
                                TextEditor(text: $store.slides[index].body)
                                    .font(GeoTheme.ui(16))
                                    .scrollContentBackground(.hidden)
                                    .frame(minHeight: 200)
                            }
                            .padding(28)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(GeoTheme.card)
                            .cornerRadius(12)
                            .shadow(color: Color.black.opacity(0.06), radius: 10, y: 4)
                        }.padding(24)
                    }
                }.background(GeoTheme.canvas)
            } else {
                WorkEmptyState(icon: "rectangle.inset.filled", title: "Create a presentation", detail: "Design local slides for talks, demos, and project pitches.") {
                    selectedID = store.addSlide()
                }
            }
        }
    }
}

// MARK: - Whiteboard Desk

struct WhiteboardDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var activeColor: Color = GeoTheme.accent
    @State private var currentPoints: [CanvasPoint] = []

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Text("Whiteboard").font(GeoTheme.serif(20))
                Spacer()
                Button("Clear Canvas") {
                    store.strokes.removeAll()
                }
                .buttonStyle(WorkActionButton(subtle: true))
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .background(GeoTheme.canvasWarm)
            Divider()

            GeometryReader { geometry in
                ZStack {
                    GeoTheme.card
                    Canvas { context, size in
                        for stroke in store.strokes {
                            var path = Path()
                            guard let first = stroke.points.first else { continue }
                            path.move(to: CGPoint(x: first.x, y: first.y))
                            for pt in stroke.points.dropFirst() {
                                path.addLine(to: CGPoint(x: pt.x, y: pt.y))
                            }
                            context.stroke(path, with: .color(GeoTheme.accent), lineWidth: stroke.width)
                        }
                        if let first = currentPoints.first {
                            var path = Path()
                            path.move(to: CGPoint(x: first.x, y: first.y))
                            for pt in currentPoints.dropFirst() {
                                path.addLine(to: CGPoint(x: pt.x, y: pt.y))
                            }
                            context.stroke(path, with: .color(GeoTheme.accent), lineWidth: 2.5)
                        }
                    }
                    .gesture(
                        DragGesture(minimumDistance: 1)
                            .onChanged { value in
                                currentPoints.append(CanvasPoint(x: value.location.x, y: value.location.y))
                            }
                            .onEnded { _ in
                                if !currentPoints.isEmpty {
                                    store.strokes.append(CanvasStroke(points: currentPoints))
                                    currentPoints = []
                                }
                            }
                    )
                }
            }
        }
    }
}

// MARK: - Calendar Desk

/// The date picker actually drives what's shown: tasks are filterable by their
/// real `dueDate`, and any task can be scheduled (or unscheduled) right here —
/// this reads and writes the same task list as the Tasks desk.
struct CalendarDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var selectedDate: Date = Date()
    @State private var newTaskTitle = ""

    private var calendar: Calendar { .current }

    private var scheduledIndices: [Int] {
        store.tasks.indices.filter { index in
            guard let due = store.tasks[index].dueDate else { return false }
            return calendar.isDate(due, inSameDayAs: selectedDate)
        }
    }

    private var unscheduledCount: Int {
        store.tasks.filter { $0.dueDate == nil }.count
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Calendar & Schedule").font(GeoTheme.serif(26))
                    Text(selectedDate, style: .date)
                        .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkSecondary)
                }
                Spacer()
                DatePicker("", selection: $selectedDate, displayedComponents: [.date])
                    .datePickerStyle(.graphical)
                    .labelsHidden()
                    .frame(width: 240)
            }
            .padding(20)
            Divider().overlay(GeoTheme.border)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 8) {
                        TextField("Schedule a task for this day…", text: $newTaskTitle)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { addScheduled() }
                        Button("Add", action: addScheduled).buttonStyle(WorkActionButton())
                    }

                    if scheduledIndices.isEmpty {
                        Text("Nothing scheduled for this day.")
                            .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkTertiary)
                            .padding(.top, 4)
                    } else {
                        Text("SCHEDULED").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                        ForEach(scheduledIndices, id: \.self) { index in
                            taskRow(index, showsDate: false)
                        }
                    }

                    if unscheduledCount > 0 {
                        Text("UNSCHEDULED").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                            .padding(.top, 8)
                        ForEach(store.tasks.indices.filter { store.tasks[$0].dueDate == nil }, id: \.self) { index in
                            taskRow(index, showsDate: true)
                        }
                    }
                }
                .padding(20)
            }
        }
        .background(GeoTheme.canvas)
    }

    private func taskRow(_ index: Int, showsDate: Bool) -> some View {
        HStack(spacing: 12) {
            Button { store.tasks[index].complete.toggle() } label: {
                Image(systemName: store.tasks[index].complete ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(store.tasks[index].complete ? GeoTheme.success : GeoTheme.inkTertiary)
            }
            .buttonStyle(.plain)
            VStack(alignment: .leading, spacing: 2) {
                Text(store.tasks[index].title).font(GeoTheme.ui(13, .medium))
                    .strikethrough(store.tasks[index].complete)
                Text(store.tasks[index].project).font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkTertiary)
            }
            Spacer()
            if showsDate {
                Button("Schedule for this day") { store.tasks[index].dueDate = selectedDate }
                    .font(GeoTheme.ui(10.5, .medium)).buttonStyle(.plain).foregroundStyle(GeoTheme.accent)
            } else {
                Button {
                    store.tasks[index].dueDate = nil
                } label: {
                    Image(systemName: "calendar.badge.minus").font(.system(size: 11))
                }
                .buttonStyle(.plain).foregroundStyle(GeoTheme.inkTertiary)
                .help("Remove from this date")
            }
        }
        .padding(12)
        .background(GeoTheme.card)
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(GeoTheme.border, lineWidth: 1))
    }

    private func addScheduled() {
        let title = newTaskTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { return }
        store.tasks.insert(WorkTask(title: title, dueDate: selectedDate), at: 0)
        newTaskTitle = ""
    }
}

// MARK: - Knowledge Base Desk

struct KnowledgeDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var selectedID: UUID?
    @State private var searchQuery: String = ""

    private var selectedIndex: Int? {
        guard let selectedID else { return store.notes.indices.first }
        return store.notes.firstIndex { $0.id == selectedID }
    }

    var body: some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    Text("KNOWLEDGE BASE").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                    Spacer()
                    Button { selectedID = store.addNote() } label: { Image(systemName: "plus") }
                        .buttonStyle(.plain).foregroundStyle(GeoTheme.accent)
                }.padding(12)

                TextField("Search wiki…", text: $searchQuery)
                    .textFieldStyle(.roundedBorder)
                    .padding(.horizontal, 10).padding(.bottom, 8)

                List(selection: $selectedID) {
                    ForEach(store.notes.filter { searchQuery.isEmpty || $0.title.localizedCaseInsensitiveContains(searchQuery) }) { note in
                        Label(note.title.isEmpty ? "Untitled Page" : note.title, systemImage: "book")
                            .font(GeoTheme.ui(12))
                            .tag(note.id)
                    }
                }.listStyle(.sidebar)
            }.frame(minWidth: 200, idealWidth: 230, maxWidth: 300)

            if let index = selectedIndex {
                VStack(spacing: 0) {
                    TextField("Page Title", text: $store.notes[index].title)
                        .font(GeoTheme.serif(24)).textFieldStyle(.plain).padding(20)
                    Divider()
                    TextEditor(text: $store.notes[index].body)
                        .font(GeoTheme.ui(13.5))
                        .scrollContentBackground(.hidden)
                        .padding(16)
                }.background(GeoTheme.card)
            } else {
                WorkEmptyState(icon: "book.closed", title: "Knowledge Base", detail: "Create interconnected notes, technical wikis, and documentation.") {
                    selectedID = store.addNote()
                }
            }
        }
    }
}

// MARK: - Work Files Desk

struct WorkFilesDesk: View {
    @ObservedObject var state: AppState
    @State private var search: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Workspace Assets").font(GeoTheme.serif(24))
                    Text(state.projectRoot).font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Spacer()
            }.padding(20)
            Divider()

            FileTreeView(
                rootPath: state.projectRoot,
                changedPaths: Set(state.filesChanged),
                onSelect: { state.openFile($0) }
            )
        }
        .background(GeoTheme.card)
    }
}

// MARK: - PDF Desk

struct PDFDesk: View {
    @State private var selectedURL: URL?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("PDF Inspector").font(GeoTheme.serif(20))
                Spacer()
                Button("Open PDF…") {
                    let panel = NSOpenPanel()
                    panel.allowedContentTypes = [.pdf]
                    panel.allowsMultipleSelection = false
                    if panel.runModal() == .OK, let url = panel.url {
                        selectedURL = url
                    }
                }
                .buttonStyle(WorkActionButton())
            }
            .padding(14).background(GeoTheme.canvasWarm)
            Divider()

            if let selectedURL {
                PDFKitRepresentable(url: selectedURL)
            } else {
                WorkEmptyState(icon: "doc.richtext.fill", title: "PDF Viewer", detail: "Open and inspect PDF documents offline with native rendering.", actionTitle: "Select PDF") {
                    let panel = NSOpenPanel()
                    panel.allowedContentTypes = [.pdf]
                    panel.allowsMultipleSelection = false
                    if panel.runModal() == .OK, let url = panel.url {
                        selectedURL = url
                    }
                }
            }
        }
    }
}

struct PDFKitRepresentable: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> PDFView {
        let pdfView = PDFView()
        pdfView.autoScales = true
        pdfView.document = PDFDocument(url: url)
        return pdfView
    }

    func updateNSView(_ nsView: PDFView, context: Context) {
        nsView.document = PDFDocument(url: url)
    }
}

// MARK: - CSV Desk

/// Parses RFC-4180-ish CSV: quoted fields, escaped `""`, and commas/newlines
/// inside quotes. Good enough for the exports and data dumps this is for
/// without pulling in a dependency.
enum CSVParser {
    static func parse(_ text: String) -> [[String]] {
        var rows: [[String]] = []
        var row: [String] = []
        var field = ""
        var inQuotes = false
        let chars = Array(text)
        var i = 0

        while i < chars.count {
            let ch = chars[i]
            if inQuotes {
                if ch == "\"" {
                    if i + 1 < chars.count, chars[i + 1] == "\"" {
                        field.append("\"")
                        i += 1
                    } else {
                        inQuotes = false
                    }
                } else {
                    field.append(ch)
                }
            } else {
                switch ch {
                case "\"": inQuotes = true
                case ",": row.append(field); field = ""
                case "\n":
                    row.append(field); field = ""
                    rows.append(row); row = []
                case "\r": break
                default: field.append(ch)
                }
            }
            i += 1
        }
        if !field.isEmpty || !row.isEmpty { row.append(field); rows.append(row) }
        return rows
    }

    static func render(_ rows: [[String]]) -> String {
        rows.map { row in
            row.map { field -> String in
                if field.contains(",") || field.contains("\"") || field.contains("\n") {
                    return "\"" + field.replacingOccurrences(of: "\"", with: "\"\"") + "\""
                }
                return field
            }.joined(separator: ",")
        }.joined(separator: "\n")
    }
}

struct CSVDesk: View {
    @State private var rows: [[String]] = []
    @State private var fileURL: URL?
    @State private var dirty = false
    @State private var loadError: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("CSV Inspector").font(GeoTheme.serif(20))
                if let fileURL {
                    Text(fileURL.lastPathComponent).font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Spacer()
                if !rows.isEmpty {
                    Text("\(rows.count) rows · \(rows.first?.count ?? 0) columns")
                        .font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Button { addRow() } label: { Label("Row", systemImage: "plus") }
                    .buttonStyle(WorkActionButton(subtle: true))
                    .disabled(rows.isEmpty)
                if dirty, let fileURL {
                    Button { save(to: fileURL) } label: { Label("Save", systemImage: "square.and.arrow.down") }
                        .buttonStyle(WorkActionButton())
                }
                Button("Open CSV…") { open() }
                    .buttonStyle(WorkActionButton(subtle: fileURL != nil))
            }
            .padding(14).background(GeoTheme.canvasWarm)
            Divider().overlay(GeoTheme.border)

            if let loadError {
                WorkEmptyState(icon: "exclamationmark.triangle", title: "Couldn't read that file", detail: loadError, actionTitle: "Try again") { open() }
            } else if rows.isEmpty {
                WorkEmptyState(icon: "tablecells", title: "CSV Inspector", detail: "Open a .csv file to view and edit it as a grid, entirely offline.", actionTitle: "Open CSV…") { open() }
            } else {
                ScrollView([.horizontal, .vertical]) {
                    VStack(spacing: 0) {
                        ForEach(rows.indices, id: \.self) { row in
                            HStack(spacing: 0) {
                                ForEach(rows[row].indices, id: \.self) { col in
                                    TextField("", text: cellBinding(row: row, col: col))
                                        .textFieldStyle(.plain)
                                        .font(row == 0 ? GeoTheme.ui(12, .bold) : GeoTheme.ui(12))
                                        .frame(width: 150, height: 32, alignment: .leading)
                                        .padding(.horizontal, 8)
                                        .background(row == 0 ? GeoTheme.sunken : GeoTheme.card)
                                        .overlay(Rectangle().stroke(GeoTheme.border, lineWidth: 0.5))
                                }
                            }
                        }
                    }
                    .padding(16)
                }
            }
        }
    }

    private func open() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.commaSeparatedText, .plainText]
        panel.allowsOtherFileTypes = true
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let text = try String(contentsOf: url, encoding: .utf8)
            let parsed = CSVParser.parse(text)
            guard !parsed.isEmpty else { throw CocoaError(.fileReadCorruptFile) }
            rows = parsed
            fileURL = url
            dirty = false
            loadError = nil
        } catch {
            loadError = "\(url.lastPathComponent) isn't readable as UTF-8 CSV text."
        }
    }

    private func save(to url: URL) {
        let text = CSVParser.render(rows)
        try? text.write(to: url, atomically: true, encoding: .utf8)
        dirty = false
    }

    private func addRow() {
        rows.append(Array(repeating: "", count: rows.first?.count ?? 1))
        dirty = true
    }

    private func cellBinding(row: Int, col: Int) -> Binding<String> {
        Binding(
            get: { row < rows.count && col < rows[row].count ? rows[row][col] : "" },
            set: { value in
                guard row < rows.count, col < rows[row].count else { return }
                rows[row][col] = value
                dirty = true
            }
        )
    }
}

// MARK: - Image Annotator Desk

/// Drag out a box on the image to label something in it. Boxes are stored
/// against the image's own path, so reopening the same file restores them.
struct ImageAnnotatorDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var imageURL: URL?
    @State private var nsImage: NSImage?
    @State private var draftBox: CGRect?
    @State private var dragStart: CGPoint?
    @State private var editingID: UUID?

    private var annotations: [ImageAnnotation] {
        guard let imageURL else { return [] }
        return store.imageAnnotations[imageURL.path] ?? []
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Image Annotator").font(GeoTheme.serif(20))
                if imageURL != nil {
                    Text("\(annotations.count) note\(annotations.count == 1 ? "" : "s") · drag to add another")
                        .font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Spacer()
                Button("Choose Image…") { chooseImage() }
                    .buttonStyle(WorkActionButton())
            }
            .padding(14).background(GeoTheme.canvasWarm)
            Divider().overlay(GeoTheme.border)

            if let imageURL, let nsImage {
                ScrollView([.horizontal, .vertical]) {
                    GeometryReader { _ in
                        ZStack(alignment: .topLeading) {
                            Image(nsImage: nsImage)
                                .resizable()
                                .aspectRatio(contentMode: .fit)

                            ForEach(annotations) { note in
                                annotationBox(note, imagePath: imageURL.path)
                            }
                            if let draftBox {
                                Rectangle()
                                    .stroke(GeoTheme.accent, style: StrokeStyle(lineWidth: 2, dash: [5, 3]))
                                    .frame(width: draftBox.width, height: draftBox.height)
                                    .position(x: draftBox.midX, y: draftBox.midY)
                            }
                        }
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 4)
                                .onChanged { value in
                                    let start = dragStart ?? value.startLocation
                                    dragStart = start
                                    draftBox = CGRect(
                                        x: min(start.x, value.location.x), y: min(start.y, value.location.y),
                                        width: abs(value.location.x - start.x), height: abs(value.location.y - start.y)
                                    )
                                }
                                .onEnded { _ in
                                    if let box = draftBox, box.width > 10, box.height > 10 {
                                        let note = ImageAnnotation(x: box.midX, y: box.midY, width: box.width, height: box.height)
                                        store.imageAnnotations[imageURL.path, default: []].append(note)
                                        editingID = note.id
                                    }
                                    draftBox = nil
                                    dragStart = nil
                                }
                        )
                    }
                    .frame(width: nsImage.size.width, height: nsImage.size.height)
                    .padding(20)
                }
                .background(GeoTheme.canvasWarm)
            } else {
                WorkEmptyState(icon: "photo", title: "Image Annotator", detail: "Load an image, then drag on it to drop a labeled note — like a lightweight markup tool.", actionTitle: "Load Image") { chooseImage() }
            }
        }
    }

    private func annotationBox(_ note: ImageAnnotation, imagePath: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if editingID == note.id {
                TextField("Label", text: labelBinding(note, imagePath: imagePath))
                    .textFieldStyle(.plain)
                    .font(GeoTheme.ui(10, .semibold))
                    .padding(3)
                    .background(.white)
                    .onSubmit { editingID = nil }
            } else {
                Text(note.label)
                    .font(GeoTheme.ui(10, .semibold))
                    .padding(.horizontal, 4).padding(.vertical, 2)
                    .background(GeoTheme.accent, in: RoundedRectangle(cornerRadius: 4))
                    .foregroundStyle(.white)
                    .onTapGesture { editingID = note.id }
            }
        }
        .overlay(alignment: .topTrailing) {
            Button {
                store.imageAnnotations[imagePath]?.removeAll { $0.id == note.id }
            } label: {
                Image(systemName: "xmark.circle.fill").font(.system(size: 12))
            }
            .buttonStyle(.plain)
            .foregroundStyle(GeoTheme.danger)
            .offset(x: 8, y: -8)
        }
        .frame(width: note.width, height: note.height, alignment: .topLeading)
        .background(GeoTheme.accent.opacity(0.12))
        .overlay(Rectangle().stroke(GeoTheme.accent, lineWidth: 2))
        .position(x: note.x, y: note.y)
    }

    private func labelBinding(_ note: ImageAnnotation, imagePath: String) -> Binding<String> {
        Binding(
            get: { store.imageAnnotations[imagePath]?.first(where: { $0.id == note.id })?.label ?? "" },
            set: { value in
                guard let index = store.imageAnnotations[imagePath]?.firstIndex(where: { $0.id == note.id }) else { return }
                store.imageAnnotations[imagePath]?[index].label = value
            }
        )
    }

    private func chooseImage() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.image]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        imageURL = url
        nsImage = NSImage(contentsOf: url)
    }
}

// MARK: - Diagram Desk

/// A flowchart canvas: nodes can be renamed, dragged, connected by dragging
/// from one node's edge onto another, and deleted. Everything persists through
/// LocalWorkspaceStore like the rest of Work mode.
struct DiagramDesk: View {
    @ObservedObject var store: LocalWorkspaceStore
    @State private var renamingID: UUID?
    @State private var linkingFrom: UUID?
    @State private var linkCursor: CGPoint?
    @State private var dragOffsets: [UUID: CGSize] = [:]

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Diagram & Flowcharts").font(GeoTheme.serif(20))
                Spacer()
                if linkingFrom != nil {
                    Text("Drag to a node to connect, or click empty space to cancel")
                        .font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.plan)
                }
                Button("Add Node") { addNode() }
                    .buttonStyle(WorkActionButton())
            }
            .padding(14).background(GeoTheme.canvasWarm)
            Divider().overlay(GeoTheme.border)

            GeometryReader { geo in
                ZStack {
                    GeoTheme.card
                        .contentShape(Rectangle())
                        .onTapGesture { linkingFrom = nil; linkCursor = nil }

                    Canvas { context, _ in
                        for link in store.diagramLinks {
                            guard let from = store.diagramNodes.first(where: { $0.id == link.from }),
                                  let to = store.diagramNodes.first(where: { $0.id == link.to }) else { continue }
                            var path = Path()
                            path.move(to: point(for: from))
                            path.addLine(to: point(for: to))
                            context.stroke(path, with: .color(GeoTheme.inkTertiary), lineWidth: 1.5)
                        }
                        if let linkingFrom, let node = store.diagramNodes.first(where: { $0.id == linkingFrom }), let linkCursor {
                            var path = Path()
                            path.move(to: point(for: node))
                            path.addLine(to: linkCursor)
                            context.stroke(path, with: .color(GeoTheme.accent), style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                        }
                    }
                    .allowsHitTesting(false)

                    ForEach(store.diagramNodes) { node in
                        nodeView(node)
                            .position(point(for: node))
                    }
                }
                .frame(width: geo.size.width, height: geo.size.height)
                .coordinateSpace(name: "diagramCanvas")
            }
        }
    }

    private func point(for node: DiagramNode) -> CGPoint {
        let offset = dragOffsets[node.id] ?? .zero
        return CGPoint(x: node.x + offset.width, y: node.y + offset.height)
    }

    private func addNode() {
        // Scatter new nodes instead of stacking them all at one fixed point.
        let x = Double.random(in: 120...420)
        let y = Double.random(in: 100...320)
        let node = DiagramNode(title: "New step", x: x, y: y)
        store.diagramNodes.append(node)
        renamingID = node.id
    }

    private func nodeView(_ node: DiagramNode) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 5) {
                Image(systemName: "gearshape.fill")
                    .font(.system(size: 13))
                    .foregroundStyle(Color(hex: node.colorHex))
                if renamingID == node.id {
                    TextField("Step", text: binding(for: node))
                        .textFieldStyle(.plain)
                        .font(GeoTheme.ui(11, .semibold))
                        .frame(width: 90)
                        .onSubmit { renamingID = nil }
                } else {
                    Text(node.title).font(GeoTheme.ui(11, .semibold))
                }
            }
            HStack(spacing: 8) {
                Button {
                    linkingFrom = node.id
                } label: {
                    Image(systemName: "arrow.triangle.branch").font(.system(size: 9))
                }
                Button { renamingID = node.id } label: {
                    Image(systemName: "pencil").font(.system(size: 9))
                }
                Button {
                    store.diagramNodes.removeAll { $0.id == node.id }
                    store.diagramLinks.removeAll { $0.from == node.id || $0.to == node.id }
                } label: {
                    Image(systemName: "trash").font(.system(size: 9))
                }
            }
            .buttonStyle(.plain)
            .foregroundStyle(GeoTheme.inkTertiary)
        }
        .padding(10)
        .background(linkingFrom == node.id ? GeoTheme.accentWash : GeoTheme.canvasWarm)
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(GeoTheme.border, lineWidth: 1))
        .contentShape(Rectangle())
        .gesture(
            DragGesture(coordinateSpace: .named("diagramCanvas"))
                .onChanged { value in
                    if let linkingFrom {
                        linkCursor = value.location
                        _ = linkingFrom
                    } else {
                        dragOffsets[node.id] = value.translation
                    }
                }
                .onEnded { value in
                    if let source = linkingFrom {
                        if let target = nodeHit(at: value.location, excluding: source) {
                            let link = DiagramLink(from: source, to: target)
                            if !store.diagramLinks.contains(link) { store.diagramLinks.append(link) }
                        }
                        linkingFrom = nil
                        linkCursor = nil
                    } else if let offset = dragOffsets[node.id],
                              let index = store.diagramNodes.firstIndex(where: { $0.id == node.id }) {
                        store.diagramNodes[index].x += offset.width
                        store.diagramNodes[index].y += offset.height
                        dragOffsets[node.id] = nil
                    }
                }
        )
    }

    private func nodeHit(at point: CGPoint, excluding: UUID) -> UUID? {
        store.diagramNodes.first { node in
            node.id != excluding && abs(node.x - point.x) < 55 && abs(node.y - point.y) < 30
        }?.id
    }

    private func binding(for node: DiagramNode) -> Binding<String> {
        Binding(
            get: { store.diagramNodes.first(where: { $0.id == node.id })?.title ?? "" },
            set: { value in
                if let index = store.diagramNodes.firstIndex(where: { $0.id == node.id }) {
                    store.diagramNodes[index].title = value
                }
            }
        )
    }
}

// MARK: - Database Desk

/// A real local SQLite browser: open a .sqlite/.db file (or create one), see
/// its tables, and run arbitrary SQL against it. No mock state — every result
/// shown here came from an actual query.
struct DatabaseDesk: View {
    @State private var browser = SQLiteBrowser()
    @State private var tables: [String] = []
    @State private var queryText = "SELECT name FROM sqlite_master WHERE type='table';"
    @State private var result: SQLiteBrowser.QueryResult?
    @State private var errorMessage: String?
    @State private var statusMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Database Browser").font(GeoTheme.serif(20))
                if browser.isOpen {
                    Text(URL(fileURLWithPath: browser.path).lastPathComponent)
                        .font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkTertiary)
                }
                Spacer()
                Button("New…") { createDatabase() }
                    .buttonStyle(WorkActionButton(subtle: true))
                Button(browser.isOpen ? "Switch…" : "Open…") { openDatabase() }
                    .buttonStyle(WorkActionButton())
            }
            .padding(14).background(GeoTheme.canvasWarm)
            Divider().overlay(GeoTheme.border)

            if !browser.isOpen {
                WorkEmptyState(
                    icon: "cylinder.split.1x2",
                    title: "Database Browser",
                    detail: "Open a SQLite (.sqlite/.db) file, or create a new one, to browse its tables and run real queries — entirely offline.",
                    actionTitle: "Open…"
                ) { openDatabase() }
            } else {
                HSplitView {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("TABLES").font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                            .padding(12)
                        if tables.isEmpty {
                            Text("No tables yet.").font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkTertiary).padding(.horizontal, 12)
                        }
                        List(tables, id: \.self) { table in
                            Button {
                                queryText = "SELECT * FROM \(table) LIMIT 200;"
                                run()
                            } label: {
                                Label(table, systemImage: "tablecells").font(GeoTheme.ui(12))
                            }
                            .buttonStyle(.plain)
                        }
                        .listStyle(.sidebar)
                    }
                    .frame(minWidth: 160, idealWidth: 190, maxWidth: 260)

                    VStack(spacing: 0) {
                        VStack(alignment: .leading, spacing: 8) {
                            TextEditor(text: $queryText)
                                .font(GeoTheme.mono(12))
                                .scrollContentBackground(.hidden)
                                .frame(height: 70)
                                .padding(8)
                                .background(GeoTheme.sunken, in: RoundedRectangle(cornerRadius: 8))
                            HStack {
                                Button("Run Query") { run() }
                                    .buttonStyle(WorkActionButton())
                                    .keyboardShortcut(.return, modifiers: .command)
                                if let statusMessage {
                                    Text(statusMessage).font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.success)
                                }
                                Spacer()
                            }
                        }
                        .padding(14)

                        Divider().overlay(GeoTheme.border)

                        if let errorMessage {
                            VStack(spacing: 8) {
                                Image(systemName: "exclamationmark.triangle").foregroundStyle(GeoTheme.danger)
                                Text(errorMessage).font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.danger)
                                    .multilineTextAlignment(.center).padding(.horizontal, 20)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else if let result {
                            resultsTable(result)
                        } else {
                            Text("Run a query to see results.")
                                .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkTertiary)
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                    }
                    .frame(minWidth: 320)
                }
            }
        }
        .background(GeoTheme.card)
        .onAppear { if browser.isOpen { run() } }
    }

    private func resultsTable(_ result: SQLiteBrowser.QueryResult) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(result.rows.isEmpty ? "0 rows" : "\(result.rows.count) row\(result.rows.count == 1 ? "" : "s")")
                .font(GeoTheme.ui(11, .medium)).foregroundStyle(GeoTheme.inkSecondary)
                .padding(.horizontal, 14).padding(.top, 10)
            if result.columns.isEmpty {
                Text("Query executed — no rows returned.")
                    .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.inkTertiary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView([.horizontal, .vertical]) {
                    VStack(alignment: .leading, spacing: 0) {
                        HStack(spacing: 0) {
                            ForEach(result.columns, id: \.self) { col in
                                Text(col).font(GeoTheme.ui(11.5, .bold))
                                    .frame(width: 150, height: 30, alignment: .leading).padding(.horizontal, 8)
                                    .background(GeoTheme.sunken)
                                    .overlay(Rectangle().stroke(GeoTheme.border, lineWidth: 0.5))
                            }
                        }
                        ForEach(Array(result.rows.enumerated()), id: \.offset) { _, row in
                            HStack(spacing: 0) {
                                ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                                    Text(cell).font(GeoTheme.mono(11.5)).lineLimit(1)
                                        .frame(width: 150, height: 28, alignment: .leading).padding(.horizontal, 8)
                                        .overlay(Rectangle().stroke(GeoTheme.border, lineWidth: 0.5))
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 14).padding(.vertical, 8)
                }
            }
        }
    }

    private func openDatabase() {
        let panel = NSOpenPanel()
        panel.allowsOtherFileTypes = true
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Open"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        connect(to: url)
    }

    private func createDatabase() {
        let panel = NSSavePanel()
        panel.allowsOtherFileTypes = true
        panel.canCreateDirectories = true
        panel.nameFieldStringValue = "workspace.sqlite"
        panel.prompt = "Create"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        connect(to: url)
    }

    private func connect(to url: URL) {
        do {
            try browser.open(url: url)
            tables = browser.tableNames()
            errorMessage = nil
            statusMessage = nil
            run()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func run() {
        guard browser.isOpen else { return }
        statusMessage = nil
        do {
            let outcome = try browser.execute(queryText)
            result = outcome
            errorMessage = nil
            tables = browser.tableNames()
            if outcome.columns.isEmpty && outcome.changedRowCount > 0 {
                statusMessage = "\(outcome.changedRowCount) row(s) affected"
            }
        } catch {
            errorMessage = error.localizedDescription
            result = nil
        }
    }
}
