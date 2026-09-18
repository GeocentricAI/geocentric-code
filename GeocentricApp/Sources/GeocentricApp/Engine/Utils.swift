import Foundation

func compactJSONString(_ value: Any?) -> String {
    guard let value else { return "" }
    if let s = value as? String { return s }
    if JSONSerialization.isValidJSONObject(value),
       let data = try? JSONSerialization.data(withJSONObject: value),
       let s = String(data: data, encoding: .utf8) {
        return s
    }
    return "\(value)"
}

/// e.g. path='app/calc.py', old_string='...' (matches the CLI's short arg summary)
func shortArgsSummary(_ args: [String: Any], limit: Int = 160) -> String {
    let parts = args.map { key, value -> String in
        let v: String
        if let s = value as? String {
            v = s.count > 60 ? String(s.prefix(60)) + "…" : s
        } else {
            v = compactJSONString(value)
        }
        return "\(key)=\(v)"
    }.sorted()
    let joined = parts.joined(separator: ", ")
    return joined.count > limit ? String(joined.prefix(limit)) + "…" : joined
}

func humanSize(_ bytes: Int) -> String {
    let gb = Double(bytes) / 1_073_741_824.0
    return String(format: "%.1fGB", gb)
}

func stringList(_ value: Any?) -> [String] {
    (value as? [Any])?.compactMap { $0 as? String } ?? []
}
