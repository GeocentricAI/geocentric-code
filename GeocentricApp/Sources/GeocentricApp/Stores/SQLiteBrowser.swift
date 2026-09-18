import Foundation
import SQLite3

/// A thin, read/write wrapper around libsqlite3 for the Database desk. Opens a
/// real .sqlite/.db file, lists its tables, and runs arbitrary SQL — this is a
/// genuine local database browser, not a decorative mock.
final class SQLiteBrowser {
    private var handle: OpaquePointer?
    private(set) var path: String = ""

    struct QueryResult {
        let columns: [String]
        let rows: [[String]]
        let changedRowCount: Int32
    }

    enum BrowserError: LocalizedError {
        case openFailed(String)
        case queryFailed(String)

        var errorDescription: String? {
            switch self {
            case .openFailed(let msg): return "Couldn't open database: \(msg)"
            case .queryFailed(let msg): return msg
            }
        }
    }

    deinit { close() }

    func open(url: URL) throws {
        close()
        var db: OpaquePointer?
        let flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE
        guard sqlite3_open_v2(url.path, &db, flags, nil) == SQLITE_OK, let db else {
            let message = db.map { String(cString: sqlite3_errmsg($0)) } ?? "unknown error"
            throw BrowserError.openFailed(message)
        }
        handle = db
        path = url.path
    }

    func close() {
        if let handle { sqlite3_close(handle) }
        handle = nil
        path = ""
    }

    var isOpen: Bool { handle != nil }

    func tableNames() -> [String] {
        (try? execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"))?
            .rows.compactMap { $0.first } ?? []
    }

    @discardableResult
    func execute(_ sql: String) throws -> QueryResult {
        guard let handle else { throw BrowserError.queryFailed("No database open.") }
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK, let statement else {
            throw BrowserError.queryFailed(String(cString: sqlite3_errmsg(handle)))
        }
        defer { sqlite3_finalize(statement) }

        let columnCount = sqlite3_column_count(statement)
        var columns: [String] = []
        for i in 0..<columnCount {
            columns.append(String(cString: sqlite3_column_name(statement, i)))
        }

        var rows: [[String]] = []
        var stepResult = sqlite3_step(statement)
        while stepResult == SQLITE_ROW {
            var row: [String] = []
            for i in 0..<columnCount {
                row.append(Self.stringValue(statement, i))
            }
            rows.append(row)
            stepResult = sqlite3_step(statement)
        }
        guard stepResult == SQLITE_DONE else {
            throw BrowserError.queryFailed(String(cString: sqlite3_errmsg(handle)))
        }

        return QueryResult(columns: columns, rows: rows, changedRowCount: sqlite3_changes(handle))
    }

    private static func stringValue(_ statement: OpaquePointer?, _ index: Int32) -> String {
        switch sqlite3_column_type(statement, index) {
        case SQLITE_NULL: return "NULL"
        case SQLITE_INTEGER: return String(sqlite3_column_int64(statement, index))
        case SQLITE_FLOAT: return String(sqlite3_column_double(statement, index))
        default:
            guard let cString = sqlite3_column_text(statement, index) else { return "" }
            return String(cString: cString)
        }
    }
}
