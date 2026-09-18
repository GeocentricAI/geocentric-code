import Foundation

/// Owns the `python3 -m geocentric.gui_bridge` subprocess and speaks its
/// newline-delimited JSON protocol. Pure I/O layer — no app state lives here;
/// see AppState for the event handling and UI-facing model.
final class GeoEngine {
    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutPipe: Pipe?
    private var stderrBuffer = Data()
    private var lineBuffer = Data()

    var onEvent: (([String: Any]) -> Void)?
    var onTerminate: ((Int32) -> Void)?
    var onStderrLine: ((String) -> Void)?

    private(set) var isRunning = false

    func start(engineRoot: String, projectRoot: String, model: String?, host: String?, yolo: Bool) {
        stop()

        let pythonCandidate = engineRoot + "/.venv/bin/python3"
        let python = FileManager.default.isExecutableFile(atPath: pythonCandidate) ? pythonCandidate : "/usr/bin/python3"

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        var args = ["-m", "geocentric.gui_bridge", "--cwd", projectRoot]
        if let model, !model.isEmpty { args += ["--model", model] }
        if let host, !host.isEmpty { args += ["--host", host] }
        if yolo { args += ["--yolo"] }
        proc.arguments = args
        proc.currentDirectoryURL = URL(fileURLWithPath: engineRoot)

        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = engineRoot
        env["PYTHONUNBUFFERED"] = "1"
        proc.environment = env

        let stdin = Pipe()
        let stdout = Pipe()
        let stderr = Pipe()
        proc.standardInput = stdin
        proc.standardOutput = stdout
        proc.standardError = stderr

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            self?.consume(data)
        }
        stderr.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                self?.onStderrLine?(text)
            }
        }
        proc.terminationHandler = { [weak self] p in
            self?.isRunning = false
            DispatchQueue.main.async {
                self?.onTerminate?(p.terminationStatus)
            }
        }

        self.process = proc
        self.stdinPipe = stdin
        self.stdoutPipe = stdout

        do {
            try proc.run()
            isRunning = true
        } catch {
            DispatchQueue.main.async {
                self.onEvent?(["type": "fatal", "message": "couldn't launch python: \(error.localizedDescription)"])
            }
        }
    }

    private func consume(_ data: Data) {
        lineBuffer.append(data)
        while let range = lineBuffer.firstRange(of: Data([0x0A])) {
            let lineData = lineBuffer.subdata(in: lineBuffer.startIndex..<range.lowerBound)
            lineBuffer.removeSubrange(lineBuffer.startIndex..<range.upperBound)
            guard !lineData.isEmpty else { continue }
            guard let obj = try? JSONSerialization.jsonObject(with: lineData) as? [String: Any] else { continue }
            DispatchQueue.main.async { [weak self] in
                self?.onEvent?(obj)
            }
        }
    }

    func send(_ command: [String: Any]) {
        guard isRunning, let handle = stdinPipe?.fileHandleForWriting else { return }
        guard var data = try? JSONSerialization.data(withJSONObject: command) else { return }
        data.append(0x0A)
        handle.write(data)
    }

    func stop() {
        if isRunning {
            send(["type": "shutdown"])
        }
        process?.terminationHandler = nil
        stdoutPipe?.fileHandleForReading.readabilityHandler = nil
        process?.terminate()
        process = nil
        stdinPipe = nil
        stdoutPipe = nil
        isRunning = false
    }

    deinit {
        stop()
    }
}
