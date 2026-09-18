import Foundation
import Combine

@MainActor
final class AppState: ObservableObject {
    // Engine plumbing
    private let engine = GeoEngine()
    @Published var connection: ConnectionState = .disconnected
    @Published var engineRoot: String {
        didSet { UserDefaults.standard.set(engineRoot, forKey: "engineRoot") }
    }
    @Published var projectRoot: String {
        didSet { UserDefaults.standard.set(projectRoot, forKey: "projectRoot") }
    }

    // Conversation
    @Published var timeline: [TimelineEntry] = []
    @Published var pendingApproval: ApprovalRequest?
    @Published var pendingQuestion: QuestionRequest?
    @Published var activePlan: PlanProposal?
    @Published var busy: Bool = false
    @Published var mascotState: MascotState = .idle
    @Published var statusLabel: String = "idle"
    @Published var workspaceMode: WorkspaceMode = .chat
    @Published private(set) var agentActivity: AgentActivity = .idle
    @Published private(set) var activeTurnID: String?
    @Published private(set) var thinkingHint: String = ""

    // Session / model / config
    @Published var currentModel: String = ""
    @Published var effort: String = "medium"
    @Published var yolo: Bool = false
    @Published var theme: String = "geocentric"
    @Published var contextWindow: Int = 0
    @Published var contextUsed: Int = 0
    @Published var contextPercent: Int = 0
    @Published var totalTokens: Int = 0
    @Published private(set) var turnStartedAt: Date?
    @Published var sessions: [SessionSummary] = []
    @Published var availableModels: [ModelInfo] = []
    @Published var availableTools: [ToolInfo] = []

    // Coding pane
    @Published var filesChanged: [String] = []
    @Published var lastDiff: (path: String, diff: String)?
    @Published var selectedFilePath: String?
    @Published var selectedFileContent: String = ""
    @Published var selectedFileIsDirty: Bool = false

    // Ollama connection
    @Published private(set) var hasOllamaApiKey: Bool = false
    @Published private(set) var ollamaHost: String = ""

    // Machine linking (see cluster.py)
    @Published private(set) var clusterLinking: Bool = false
    @Published private(set) var clusterPeers: [ClusterPeer] = []
    @Published private(set) var clusterPairedPeer: ClusterPeer?
    @Published private(set) var clusterIncomingRequest: ClusterPeer?
    @Published private(set) var clusterMode: ClusterMode?
    @Published private(set) var clusterError: String = ""

    // Geo's presence — all three are pure client-side display preferences,
    // nothing the engine needs to know about.
    @Published var mascotVisible: Bool {
        didSet { UserDefaults.standard.set(mascotVisible, forKey: "mascotVisible") }
    }
    @Published var mascotAlwaysVisible: Bool {
        didSet { UserDefaults.standard.set(mascotAlwaysVisible, forKey: "mascotAlwaysVisible") }
    }
    @Published var mascotFloating: Bool {
        didSet {
            UserDefaults.standard.set(mascotFloating, forKey: "mascotFloating")
            GeoFloatingPanel.shared.setVisible(mascotFloating && mascotVisible, state: self)
        }
    }

    private var currentAssistantEntry: TimelineEntry?
    private var toolRecordsById: [String: ToolCallRecord] = [:]
    /// Reasoning collected across the *whole* turn, including any legs before
    /// or between tool calls — attached to whichever assistant entry actually
    /// ends up with visible text, since an entry that never gets real content
    /// (e.g. a thinking-only leg right before a tool call) never renders.
    private var turnThinkingText: String = ""

    /// Set while the app is deliberately tearing the engine down, so a normal
    /// shutdown is never mistaken for a crash worth recovering from.
    private var isShuttingDown = false
    /// Guards the automatic relaunch so a persistently broken engine reports the
    /// failure instead of restarting forever.
    private var hasAttemptedEngineRestart = false

    /// How the current turn ended, decided by whichever of "error" /
    /// "interrupted" fires before the closing "status: idle" — read once
    /// there and reset. nil means it ended cleanly.
    private enum TurnOutcome { case error, interrupted }
    private var turnOutcome: TurnOutcome?
    private var mascotFlashWorkItem: DispatchWorkItem?

    /// Where the mascot settles once nothing transient (a flash, an active
    /// turn) is claiming it.
    private var restingMascotState: MascotState {
        (pendingApproval != nil || pendingQuestion != nil) ? .waiting : .idle
    }

    /// Shows `pose` immediately, then hands the mascot back to whatever it
    /// should rest on — unless a new turn has already started by then, in
    /// which case that turn's own state (already applied) wins and this is a
    /// no-op rather than an incorrect clobber.
    private func flashMascot(_ pose: MascotState, duration: TimeInterval = 1.3) {
        mascotFlashWorkItem?.cancel()
        mascotState = pose
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.busy else { return }
            self.mascotState = self.restingMascotState
        }
        mascotFlashWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + duration, execute: work)
    }

    init() {
        let defaults = UserDefaults.standard
        // install.sh always writes both of these explicitly, so a proper
        // install never touches this fallback at all - it only matters for a
        // build run straight from source, where the dev's own checkout is a
        // reasonable guess.
        let devCheckout = "/Users/elywright/Documents/Geocentric Code"
        let portableDefault = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Geocentric").path
        let fallbackEngineRoot = FileManager.default.fileExists(atPath: devCheckout) ? devCheckout : portableDefault
        self.engineRoot = defaults.string(forKey: "engineRoot") ?? fallbackEngineRoot
        self.projectRoot = defaults.string(forKey: "projectRoot")
            ?? defaults.string(forKey: "engineRoot")
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents").path
        self.mascotVisible = defaults.object(forKey: "mascotVisible") as? Bool ?? true
        self.mascotAlwaysVisible = defaults.bool(forKey: "mascotAlwaysVisible")
        self.mascotFloating = defaults.bool(forKey: "mascotFloating")

        engine.onEvent = { [weak self] event in
            self?.handle(event)
        }
        engine.onTerminate = { [weak self] code in
            guard let self else { return }
            // However the engine went down, the turn it was running is over.
            self.resetTurnPresentation()

            if self.isShuttingDown { return }
            if case .fatal = self.connection { return }

            // A crashed engine is recoverable: relaunch once, silently, and keep
            // the transcript. Only bother the user if the retry also fails.
            if !self.hasAttemptedEngineRestart {
                self.hasAttemptedEngineRestart = true
                self.connection = .connecting
                self.addNote("Reconnecting to the local engine…", style: .info)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                    guard let self, !self.isShuttingDown else { return }
                    self.engine.start(engineRoot: self.engineRoot, projectRoot: self.projectRoot,
                                      model: nil, host: nil, yolo: self.yolo)
                }
                return
            }

            self.connection = .fatal("The local engine stopped unexpectedly (exit code \(code)).")
        }
        engine.onStderrLine = { [weak self] line in
            // Only surface genuinely unexpected stderr, not the requests warning noise.
            if line.contains("Traceback") || line.contains("Error") {
                self?.addNote(line.trimmingCharacters(in: .whitespacesAndNewlines), style: .error)
            }
        }

        // Property observers don't fire for an initializer's own assignment,
        // so a restored "floating" preference needs one explicit kick here.
        if mascotFloating && mascotVisible {
            GeoFloatingPanel.shared.setVisible(true, state: self)
        }
    }

    func setOllamaApiKey(_ key: String) {
        engine.send(["type": "set_ollama_api_key", "key": key])
    }

    func useOllamaCloud() {
        engine.send(["type": "set_ollama_host", "host": "https://ollama.com"])
    }

    func useLocalOllama() {
        engine.send(["type": "set_ollama_host", "host": "http://localhost:11434"])
    }

    // MARK: - Machine linking

    func startLinking() {
        clusterPeers = []
        clusterPairedPeer = nil
        clusterMode = nil
        clusterError = ""
        engine.send(["type": "cluster_link_start"])
    }

    func stopLinking() {
        engine.send(["type": "cluster_link_stop"])
        clusterLinking = false
        clusterPeers = []
        clusterPairedPeer = nil
        clusterMode = nil
    }

    func requestPairing(_ peer: ClusterPeer) {
        engine.send(["type": "cluster_pair_request", "id": peer.id])
    }

    func answerPairing(accept: Bool) {
        guard let request = clusterIncomingRequest else { return }
        engine.send(["type": "cluster_pair_answer", "id": request.id, "accept": accept])
        clusterIncomingRequest = nil
    }

    func setClusterMode(_ mode: ClusterMode?) {
        engine.send(["type": "cluster_set_mode", "mode": mode?.rawValue ?? ""])
    }

    // MARK: - Lifecycle

    func connect() {
        connection = .connecting
        timeline.removeAll()
        resetTurnPresentation()
        isShuttingDown = false
        hasAttemptedEngineRestart = false

        let root = engineRoot
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            Self.ensureEngineReady(engineRoot: root)
            DispatchQueue.main.async {
                guard let self, !self.isShuttingDown else { return }
                self.engine.start(engineRoot: self.engineRoot, projectRoot: self.projectRoot,
                                  model: nil, host: nil, yolo: self.yolo)
            }
        }
    }

    /// First-launch setup, run once per engineRoot: extracts the Python
    /// backend bundled inside this app and provisions a virtualenv for it, so
    /// a plain downloaded-and-unzipped release works on its own — install.sh
    /// does the same provisioning ahead of time, making this a no-op for
    /// anyone who ran it. Runs off the main thread; `connect()` only calls
    /// back into `engine.start` once this returns.
    nonisolated private static func ensureEngineReady(engineRoot: String) {
        let fm = FileManager.default
        let root = URL(fileURLWithPath: engineRoot)
        let packageMarker = root.appendingPathComponent("geocentric/__init__.py")
        if !fm.fileExists(atPath: packageMarker.path), let bundle = AppResources.bundle {
            if let bundledPackage = bundle.url(forResource: "geocentric", withExtension: nil, subdirectory: "PythonEngine") {
                try? fm.createDirectory(at: root, withIntermediateDirectories: true)
                try? fm.removeItem(at: root.appendingPathComponent("geocentric"))
                try? fm.copyItem(at: bundledPackage, to: root.appendingPathComponent("geocentric"))
            }
            if let bundledPyproject = bundle.url(forResource: "pyproject", withExtension: "toml", subdirectory: "PythonEngine") {
                try? fm.removeItem(at: root.appendingPathComponent("pyproject.toml"))
                try? fm.copyItem(at: bundledPyproject, to: root.appendingPathComponent("pyproject.toml"))
            }
        }

        let venvPython = root.appendingPathComponent(".venv/bin/python3").path
        guard !fm.isExecutableFile(atPath: venvPython) else { return }
        guard fm.isExecutableFile(atPath: "/usr/bin/python3") else { return }

        let venv = Process()
        venv.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        venv.arguments = ["-m", "venv", root.appendingPathComponent(".venv").path]
        try? venv.run()
        venv.waitUntilExit()

        guard fm.isExecutableFile(atPath: venvPython) else { return }
        let pip = Process()
        pip.executableURL = root.appendingPathComponent(".venv/bin/pip")
        pip.arguments = [
            "install", "--quiet",
            "rich>=13.7", "prompt_toolkit>=3.0.43", "requests>=2.31", "urllib3<2", "pygments>=2.17",
        ]
        try? pip.run()
        pip.waitUntilExit()
    }

    func disconnect() {
        isShuttingDown = true
        engine.stop()
        connection = .disconnected
    }

    func reconnectToNewProject(_ path: String) {
        projectRoot = path
        connect()
    }

    // MARK: - Native editor

    func openFile(_ url: URL) {
        guard !url.hasDirectoryPath else { return }
        selectedFilePath = displayPath(for: url)
        selectedFileContent = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
        selectedFileIsDirty = false
    }

    func saveSelectedFile() {
        guard selectedFileIsDirty, let selectedFilePath else { return }
        let url = selectedFilePath.hasPrefix("/")
            ? URL(fileURLWithPath: selectedFilePath)
            : URL(fileURLWithPath: projectRoot).appendingPathComponent(selectedFilePath)
        do {
            try selectedFileContent.write(to: url, atomically: true, encoding: .utf8)
            selectedFileIsDirty = false
            if !filesChanged.contains(url.path) { filesChanged.append(url.path) }
            addNote("Saved \(displayPath(for: url)).", style: .success)
        } catch {
            addNote("Couldn't save \(displayPath(for: url)): \(error.localizedDescription)", style: .error)
        }
    }

    // MARK: - Sending commands

    /// Chat and Code are separate conversations, not one transcript with a
    /// label on it — the same split as the Python side's `mode_histories`
    /// (see gui_bridge.py). Switching modes swaps which transcript is showing
    /// rather than continuing to append to a shared one.
    private var modeTimelines: [WorkspaceMode: [TimelineEntry]] = [:]

    func setWorkspaceMode(_ mode: WorkspaceMode) {
        guard workspaceMode != mode else { return }
        modeTimelines[workspaceMode] = timeline
        workspaceMode = mode
        timeline = modeTimelines[mode] ?? []
        pendingApproval = nil
        pendingQuestion = nil
        activePlan = nil
        resetTurnPresentation()
        engine.send(["type": "set_mode", "mode": mode.rawValue])
    }

    func sendMessage(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        if let q = pendingQuestion, !trimmed.hasPrefix("/") {
            answerQuestionByText(trimmed, question: q)
            return
        }

        let turnID = UUID().uuidString
        activeTurnID = turnID
        currentAssistantEntry = nil
        thinkingHint = ""
        turnThinkingText = ""
        agentActivity = .preparing
        busy = true
        mascotState = .pondering
        statusLabel = "preparing"

        if !trimmed.hasPrefix("/") {
            let entry = TimelineEntry(kind: .userMessage)
            entry.text = trimmed
            timeline.append(entry)
        }
        engine.send([
            "type": "send_message", "text": trimmed,
            "turn_id": turnID, "mode": workspaceMode.rawValue,
        ])
    }

    func interrupt() {
        engine.send(["type": "interrupt"])
    }

    func respondToApproval(_ decision: String) {
        engine.send(["type": "approve", "decision": decision])
        pendingApproval = nil
        if busy { mascotState = .active }
    }

    func answerQuestionByText(_ text: String, question: QuestionRequest) {
        let entry = TimelineEntry(kind: .userMessage)
        entry.text = text
        timeline.append(entry)
        if question.multiSelect {
            let tokens = text.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
            let matched = tokens.compactMap { resolveOption($0, in: question.options) }
            engine.send(["type": "answer_question", "answer": matched])
        } else {
            if let matched = resolveOption(text, in: question.options) {
                engine.send(["type": "answer_question", "answer": matched])
            }
        }
        pendingQuestion = nil
        if busy { mascotState = .active }
    }

    func answerQuestion(option: QuestionOption, question: QuestionRequest) {
        let entry = TimelineEntry(kind: .userMessage)
        entry.text = option.label
        timeline.append(entry)
        if question.multiSelect {
            engine.send(["type": "answer_question", "answer": [option.label]])
        } else {
            engine.send(["type": "answer_question", "answer": option.label])
        }
        pendingQuestion = nil
        if busy { mascotState = .active }
    }

    private func resolveOption(_ token: String, in options: [QuestionOption]) -> String? {
        if let n = Int(token), n >= 1, n <= options.count { return options[n - 1].label }
        return options.first { $0.label.lowercased().hasPrefix(token.lowercased()) }?.label
    }

    func setModel(_ name: String) {
        engine.send(["type": "set_model", "name": name])
    }

    func setEffort(_ level: String) {
        engine.send(["type": "set_effort", "level": level])
    }

    func setYolo(_ value: Bool) {
        yolo = value
        engine.send(["type": "set_yolo", "value": value])
    }

    func setTheme(_ name: String) {
        engine.send(["type": "set_theme", "name": name])
    }

    func refreshModels() {
        engine.send(["type": "list_models"])
    }

    func refreshSessions() {
        engine.send(["type": "list_sessions"])
    }

    func refreshTools() {
        engine.send(["type": "list_tools"])
    }

    func newSession() {
        timeline.removeAll()
        engine.send(["type": "new_session"])
    }

    func resumeSession(_ id: String) {
        timeline.removeAll()
        engine.send(["type": "resume_session", "id": id])
    }

    func acceptPlan(auto: Bool) {
        activePlan = nil
        beginControlTurn()
        engine.send(["type": "accept_plan", "mode": auto ? "auto" : "manual", "turn_id": activeTurnID ?? ""])
    }

    func revisePlan(feedback: String) {
        activePlan = nil
        beginControlTurn()
        let entry = TimelineEntry(kind: .userMessage)
        entry.text = feedback
        timeline.append(entry)
        engine.send(["type": "revise_plan", "feedback": feedback, "turn_id": activeTurnID ?? ""])
    }

    func cancelPlan() {
        activePlan = nil
        engine.send(["type": "cancel_plan"])
    }

    // MARK: - Event handling

    private func handle(_ event: [String: Any]) {
        guard let type = event["type"] as? String else { return }
        let turnID = event["turn_id"] as? String ?? ""
        if isTurnScoped(type), !accepts(turnID: turnID) { return }

        switch type {
        case "ready":
            currentModel = event["model"] as? String ?? ""
            effort = event["effort"] as? String ?? "medium"
            yolo = event["yolo"] as? Bool ?? false
            theme = event["theme"] as? String ?? "geocentric"
            contextWindow = event["context_window"] as? Int ?? 0
            hasOllamaApiKey = event["has_ollama_api_key"] as? Bool ?? false
            ollamaHost = event["ollama_host"] as? String ?? ollamaHost
            // `ready` always follows the reachability probe, so it must not
            // overwrite an unreachable verdict with a false all-clear.
            if event["ollama_reachable"] as? Bool == false {
                connection = .ollamaUnreachable(host: event["ollama_host"] as? String ?? "localhost:11434")
            } else {
                connection = .ready
                refreshSessions()
                engine.send(["type": "set_mode", "mode": workspaceMode.rawValue])
            }

        case "ollama_unreachable":
            connection = .ollamaUnreachable(host: event["host"] as? String ?? "")

        case "fatal":
            connection = .fatal(event["message"] as? String ?? "unknown error")

        case "status":
            let state = event["state"] as? String ?? "idle"
            statusLabel = state
            switch state {
            case "idle":
                let wasBusy = busy
                busy = false
                agentActivity = .idle
                thinkingHint = ""
                timeline.forEach { $0.isStreaming = false }
                currentAssistantEntry?.isStreaming = false
                currentAssistantEntry = nil
                activeTurnID = nil
                turnStartedAt = nil
                // Only a turn that actually ran (busy was true) earns a
                // reaction — this also fires for no-op idle events that
                // shouldn't make Geo cheer about nothing.
                if wasBusy {
                    switch turnOutcome {
                    case .error: flashMascot(.worried)
                    case .interrupted: mascotState = restingMascotState
                    case nil: flashMascot(.celebrating)
                    }
                } else {
                    mascotState = restingMascotState
                }
                turnOutcome = nil
            case "thinking":
                busy = true
                agentActivity = .thinking
                mascotState = .pondering
                thinkingHint = thinkingHint.isEmpty ? "Geo is thinking through the next step" : thinkingHint
                if turnStartedAt == nil { turnStartedAt = .now }
            case "tool_running":
                busy = true
                mascotState = .active
                if turnStartedAt == nil { turnStartedAt = .now }
            default:
                busy = true
                agentActivity = .preparing
                if turnStartedAt == nil { turnStartedAt = .now }
                mascotState = .pondering
            }

        case "assistant_delta":
            let delta = event["text"] as? String ?? ""
            mascotState = .active
            ensureAssistantEntry().text += delta

        case "thinking_delta":
            // Kept and shown behind a collapsible disclosure on the settled
            // reply (see TranscriptRow/MessageBubbleView) — the user asked to
            // be able to see it, not just a hint string. Buffered on the turn
            // rather than the current entry: a thinking leg that happens
            // right before a tool call has no entry of its own yet (and
            // never will, if it produces no text), so it has to be attached
            // to whichever entry eventually carries the real answer.
            let delta = event["text"] as? String ?? ""
            busy = true
            agentActivity = .thinking
            mascotState = .pondering
            thinkingHint = "Geo is considering the best next step"
            turnThinkingText += delta
            currentAssistantEntry?.thinkingText = turnThinkingText

        case "assistant_final":
            let entry = ensureAssistantEntry()
            entry.text = event["text"] as? String ?? entry.text
            entry.isStreaming = false
            currentAssistantEntry = nil
            thinkingHint = ""

        case "tool_call":
            let id = event["id"] as? String ?? UUID().uuidString
            let name = event["name"] as? String ?? "tool"
            let args = event["args"] as? [String: Any] ?? [:]
            let pathHint: String
            if let path = args["path"] as? String, !path.isEmpty {
                pathHint = URL(fileURLWithPath: path).lastPathComponent
            } else {
                pathHint = (args["pattern"] as? String) ?? (args["command"] as? String) ?? ""
            }
            let record = ToolCallRecord(id: id, name: name, argsText: shortArgsSummary(args), pathHint: pathHint)
            toolRecordsById[id] = record
            let entry = TimelineEntry(id: "tool-\(id)", kind: .toolCall)
            entry.toolCall = record
            timeline.append(entry)
            currentAssistantEntry = nil
            agentActivity = .usingTool(name)
            busy = true
            mascotState = .active
            thinkingHint = "Geo is working with \(name)"

        case "tool_result":
            let id = event["id"] as? String ?? ""
            guard let record = toolRecordsById[id] else { break }
            let ok = event["ok"] as? Bool ?? false
            record.status = ok ? .ok : .failed
            record.outputText = event["output"] as? String ?? ""
            record.diffText = event["diff"] as? String
            if let diff = record.diffText, !diff.isEmpty {
                let meta = event["meta"] as? [String: Any] ?? [:]
                let path = meta["path"] as? String ?? record.name
                lastDiff = (path, diff)
                if !filesChanged.contains(path) { filesChanged.append(path) }
                selectedFilePath = path
            }

        case "todo_update":
            let todos = (event["todos"] as? [[String: Any]]) ?? []
            let lines = todos.map { t -> String in
                let status = t["status"] as? String ?? "pending"
                let mark = status == "completed" ? "[x]" : (status == "in_progress" ? "[~]" : "[ ]")
                return "\(mark) \(t["content"] as? String ?? "")"
            }
            let entry = TimelineEntry(kind: .note)
            entry.text = "Task list — " + (lines.isEmpty ? "empty" : "\n" + lines.joined(separator: "\n"))
            entry.style = .info
            timeline.append(entry)

        case "plan_proposal":
            let plan = PlanProposal(
                raw: event["text"] as? String ?? "",
                goal: event["goal"] as? String ?? "",
                files: stringList(event["files"]),
                steps: stringList(event["steps"]),
                risks: event["risks"] as? String ?? "",
                verification: event["verification"] as? String ?? "",
                structured: event["structured"] as? Bool ?? false
            )
            activePlan = plan
            currentAssistantEntry = nil
            thinkingHint = ""

        case "approval_request":
            pendingApproval = ApprovalRequest(
                id: event["id"] as? String ?? UUID().uuidString,
                tool: event["tool"] as? String ?? "",
                argsText: shortArgsSummary(event["args"] as? [String: Any] ?? [:]),
                danger: event["danger"] as? String ?? "low",
                reasons: stringList(event["reasons"])
            )
            busy = true
            agentActivity = .waitingForApproval
            mascotState = .waiting
            thinkingHint = "Geo needs your approval to continue"

        case "approval_resolved":
            pendingApproval = nil
            if busy { mascotState = .active }

        case "question_request":
            let opts = (event["options"] as? [[String: Any]] ?? []).map {
                QuestionOption(label: $0["label"] as? String ?? "", description: $0["description"] as? String ?? "")
            }
            pendingQuestion = QuestionRequest(
                question: event["question"] as? String ?? "",
                options: opts,
                multiSelect: event["multi_select"] as? Bool ?? false
            )
            mascotState = .waiting

        case "mentions":
            let paths = stringList(event["paths"])
            if !paths.isEmpty {
                addNote("Attached: " + paths.joined(separator: ", "), style: .info)
            }

        case "command_output":
            let entry = TimelineEntry(kind: .commandOutput)
            entry.text = event["text"] as? String ?? ""
            timeline.append(entry)

        case "error":
            let raw = event["message"] as? String ?? "unknown error"
            turnOutcome = .error
            // A dead Ollama surfaces as a wall of urllib3 traceback text. That
            // belongs in the overlay as one sentence, not in the transcript.
            if raw.contains("Connection refused") || raw.lowercased().contains("max retries") {
                connection = .ollamaUnreachable(host: "http://localhost:11434")
            } else {
                addNote(raw, style: .error)
            }
            currentAssistantEntry = nil
            resetTurnPresentation()

        case "interrupted":
            turnOutcome = .interrupted
            addNote("Interrupted.", style: .warn)
            currentAssistantEntry = nil
            resetTurnPresentation()

        case "turn_finished":
            resetTurnPresentation()

        case "stats":
            contextUsed = event["context_used"] as? Int ?? contextUsed
            contextWindow = event["context_window"] as? Int ?? contextWindow
            contextPercent = event["context_percent"] as? Int ?? contextPercent
            totalTokens = event["total_tokens"] as? Int ?? totalTokens

        case "model_changed":
            currentModel = event["name"] as? String ?? currentModel
            contextWindow = event["context_window"] as? Int ?? contextWindow

        case "effort_changed":
            effort = event["level"] as? String ?? effort

        case "yolo_changed":
            yolo = event["value"] as? Bool ?? yolo

        case "ollama_api_key_changed":
            hasOllamaApiKey = event["has_key"] as? Bool ?? hasOllamaApiKey

        case "ollama_host_changed":
            ollamaHost = event["host"] as? String ?? ollamaHost
            if event["ollama_reachable"] as? Bool == false {
                addNote("Can't reach \(ollamaHost) yet.", style: .warn)
            } else {
                addNote("Now using \(ollamaHost).", style: .success)
            }

        case "cluster_linking_started":
            clusterLinking = true

        case "cluster_linking_stopped":
            clusterLinking = false

        case "cluster_peer_found":
            let peer = ClusterPeer(id: event["id"] as? String ?? "", name: event["name"] as? String ?? "Unknown Mac",
                                    address: event["address"] as? String ?? "")
            if !clusterPeers.contains(where: { $0.id == peer.id }) { clusterPeers.append(peer) }

        case "cluster_peer_lost":
            let id = event["id"] as? String ?? ""
            clusterPeers.removeAll { $0.id == id }

        case "cluster_pair_incoming":
            clusterIncomingRequest = ClusterPeer(id: event["id"] as? String ?? "", name: event["name"] as? String ?? "Unknown Mac",
                                                  address: event["address"] as? String ?? "")

        case "cluster_paired":
            let peer = ClusterPeer(id: event["id"] as? String ?? "", name: event["name"] as? String ?? "Unknown Mac",
                                    address: "", paired: true)
            clusterPairedPeer = peer
            clusterIncomingRequest = nil
            addNote("Paired with \(peer.name).", style: .success)

        case "cluster_pair_declined":
            addNote("Pairing was declined.", style: .warn)

        case "cluster_unpaired":
            clusterPairedPeer = nil
            clusterMode = nil
            addNote("\(event["name"] as? String ?? "The other Mac") disconnected.", style: .warn)

        case "cluster_mode_changed":
            let raw = event["mode"] as? String ?? ""
            clusterMode = ClusterMode(rawValue: raw)

        case "cluster_mode_error":
            clusterError = event["message"] as? String ?? "Couldn't switch modes."
            addNote(clusterError, style: .error)

        case "cluster_task_received":
            addNote("Working on a task delegated from the paired Mac.", style: .info)

        case "cluster_task_finished":
            break

        case "theme_changed":
            theme = event["name"] as? String ?? theme

        case "models":
            let list = (event["models"] as? [[String: Any]]) ?? []
            availableModels = list.map {
                ModelInfo(
                    name: $0["name"] as? String ?? "",
                    sizeBytes: $0["size"] as? Int ?? 0,
                    supportsTools: $0["tools"] as? Bool ?? false,
                    supportsThinking: $0["thinking"] as? Bool ?? false
                )
            }

        case "sessions":
            let list = (event["sessions"] as? [[String: Any]]) ?? []
            sessions = list.map {
                SessionSummary(
                    id: $0["id"] as? String ?? "",
                    when: $0["when"] as? String ?? "",
                    age: $0["age"] as? String ?? "",
                    turns: $0["turns"] as? Int ?? 0,
                    model: $0["model"] as? String ?? "",
                    title: $0["title"] as? String ?? ""
                )
            }

        case "tools":
            let list = (event["tools"] as? [[String: Any]]) ?? []
            availableTools = list.map {
                ToolInfo(
                    name: $0["name"] as? String ?? "",
                    description: $0["description"] as? String ?? "",
                    danger: $0["danger"] as? String ?? "low",
                    mutating: $0["mutating"] as? Bool ?? false,
                    group: $0["group"] as? String ?? "general"
                )
            }

        case "history":
            let entries = (event["entries"] as? [[String: Any]]) ?? []
            timeline = entries.compactMap { e -> TimelineEntry? in
                let text = e["text"] as? String ?? ""
                guard !text.isEmpty else { return nil }
                let entry = TimelineEntry(kind: e["role"] as? String == "user" ? .userMessage : .assistantMessage)
                entry.text = text
                return entry
            }

        case "session_new", "session_resumed":
            refreshSessions()

        case "mode_changed":
            if let mode = event["mode"] as? String, let parsed = WorkspaceMode(rawValue: mode) {
                workspaceMode = parsed
            }

        case "quit":
            break

        default:
            break
        }
    }

    private func ensureAssistantEntry() -> TimelineEntry {
        if let e = currentAssistantEntry { return e }
        let entry = TimelineEntry(kind: .assistantMessage)
        entry.isStreaming = true
        entry.thinkingText = turnThinkingText
        timeline.append(entry)
        currentAssistantEntry = entry
        return entry
    }

    private func addNote(_ text: String, style: NoteStyle) {
        let entry = TimelineEntry(kind: .note)
        entry.text = text
        entry.style = style
        timeline.append(entry)
    }

    private func displayPath(for url: URL) -> String {
        let full = url.path
        let root = URL(fileURLWithPath: projectRoot).standardizedFileURL.path
        guard full.hasPrefix(root + "/") else { return full }
        return String(full.dropFirst(root.count + 1))
    }

    private func beginControlTurn() {
        let id = UUID().uuidString
        activeTurnID = id
        busy = true
        agentActivity = .preparing
        mascotState = .pondering
        statusLabel = "preparing"
        thinkingHint = ""
        turnThinkingText = ""
        turnStartedAt = .now
    }

    /// Returns every transient indicator to rest and clears out any assistant
    /// bubble the turn opened but never filled. Called on *every* way a turn can
    /// end — final answer, error, interrupt, or the engine dying — so a stalled
    /// turn can never strand a permanently-"thinking" row in the transcript.
    private func resetTurnPresentation() {
        mascotFlashWorkItem?.cancel()
        busy = false
        agentActivity = .idle
        mascotState = restingMascotState
        statusLabel = "idle"
        thinkingHint = ""
        turnThinkingText = ""
        activeTurnID = nil
        turnStartedAt = nil
        currentAssistantEntry = nil

        timeline.forEach { $0.isStreaming = false }
        timeline.removeAll { entry in
            entry.kind == .assistantMessage
                && entry.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }

    private func isTurnScoped(_ type: String) -> Bool {
        [
            "status", "assistant_delta", "thinking_delta", "assistant_final",
            "tool_call", "tool_result", "todo_update", "plan_proposal",
            "approval_request", "approval_resolved", "question_request", "mentions",
            "error", "interrupted", "stats", "turn_finished",
        ].contains(type)
    }

    private func accepts(turnID: String) -> Bool {
        guard let activeTurnID else { return false }
        return !turnID.isEmpty && turnID == activeTurnID
    }
}
