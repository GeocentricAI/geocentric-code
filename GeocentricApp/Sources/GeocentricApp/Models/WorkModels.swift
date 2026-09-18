import Foundation
import CoreGraphics

struct WorkDocument: Identifiable, Codable, Equatable {
    var id: UUID
    var title: String
    var plainText: String
    var rtfData: Data
    var modifiedAt: Date

    init(id: UUID = UUID(), title: String, plainText: String = "", rtfData: Data = Data(), modifiedAt: Date = .now) {
        self.id = id
        self.title = title
        self.plainText = plainText
        self.rtfData = rtfData
        self.modifiedAt = modifiedAt
    }
}

struct WorkNote: Identifiable, Codable, Equatable {
    var id: UUID
    var title: String
    var body: String
    var updatedAt: Date

    init(id: UUID = UUID(), title: String, body: String, updatedAt: Date = .now) {
        self.id = id
        self.title = title
        self.body = body
        self.updatedAt = updatedAt
    }
}

struct WorkTask: Identifiable, Codable, Equatable {
    var id: UUID
    var title: String
    var complete: Bool
    var dueDate: Date?
    var project: String

    init(id: UUID = UUID(), title: String, complete: Bool = false, dueDate: Date? = nil, project: String = "Inbox") {
        self.id = id
        self.title = title
        self.complete = complete
        self.dueDate = dueDate
        self.project = project
    }
}

enum BoardColumn: String, CaseIterable, Codable, Identifiable {
    case inbox = "Inbox"
    case doing = "In progress"
    case done = "Done"
    var id: String { rawValue }
}

struct BoardCard: Identifiable, Codable, Equatable {
    var id: UUID
    var title: String
    var column: BoardColumn
    var detail: String

    init(id: UUID = UUID(), title: String, column: BoardColumn = .inbox, detail: String = "") {
        self.id = id
        self.title = title
        self.column = column
        self.detail = detail
    }
}

struct WorkSheet: Identifiable, Codable, Equatable {
    var id: UUID
    var title: String
    var cells: [[String]]

    init(id: UUID = UUID(), title: String, cells: [[String]]) {
        self.id = id
        self.title = title
        self.cells = cells
    }
}

struct WorkSlide: Identifiable, Codable, Equatable {
    var id: UUID
    var title: String
    var body: String
    var accentHex: UInt32

    init(id: UUID = UUID(), title: String, body: String, accentHex: UInt32 = 0xD97757) {
        self.id = id
        self.title = title
        self.body = body
        self.accentHex = accentHex
    }
}

struct CanvasStroke: Identifiable, Codable, Equatable {
    var id: UUID
    var points: [CanvasPoint]
    var colorHex: UInt32
    var width: Double

    init(id: UUID = UUID(), points: [CanvasPoint], colorHex: UInt32 = 0x1F1E1D, width: Double = 2.5) {
        self.id = id
        self.points = points
        self.colorHex = colorHex
        self.width = width
    }
}

struct CanvasPoint: Codable, Equatable {
    var x: Double
    var y: Double
}

struct DiagramNode: Identifiable, Codable, Equatable {
    var id: UUID
    var title: String
    var x: Double
    var y: Double
    var colorHex: UInt32

    init(id: UUID = UUID(), title: String, x: Double, y: Double, colorHex: UInt32 = 0x6B5B95) {
        self.id = id
        self.title = title
        self.x = x
        self.y = y
        self.colorHex = colorHex
    }
}

struct DiagramLink: Identifiable, Codable, Equatable {
    var id: UUID
    var from: UUID
    var to: UUID

    init(id: UUID = UUID(), from: UUID, to: UUID) {
        self.id = id
        self.from = from
        self.to = to
    }

    static func == (lhs: DiagramLink, rhs: DiagramLink) -> Bool {
        (lhs.from == rhs.from && lhs.to == rhs.to) || (lhs.from == rhs.to && lhs.to == rhs.from)
    }
}

struct ImageAnnotation: Identifiable, Codable, Equatable {
    var id: UUID
    var x: Double
    var y: Double
    var width: Double
    var height: Double
    var label: String

    init(id: UUID = UUID(), x: Double, y: Double, width: Double, height: Double, label: String = "Note") {
        self.id = id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.label = label
    }
}
