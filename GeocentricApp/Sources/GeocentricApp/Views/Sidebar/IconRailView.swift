import SwiftUI

/// The thin always-visible icon strip on the far left.
struct IconRailView: View {
    @ObservedObject var state: AppState
    @Binding var panel: RailPanel?

    var body: some View {
        VStack(spacing: 3) {
            RailIconButton(icon: "plus", help: "New session") { state.newSession() }
                .padding(.bottom, 5)

            RailIconButton(icon: "bubble.left.and.bubble.right",
                           active: panel == .sessions, help: "Sessions") {
                toggle(.sessions)
            }
            RailIconButton(icon: "wrench.and.screwdriver",
                           active: panel == .tools, help: "Tools") {
                toggle(.tools)
                state.refreshTools()
            }
            RailIconButton(icon: "network",
                           active: panel == .machines, help: "Machines") {
                toggle(.machines)
            }
            RailIconButton(icon: "slider.horizontal.3",
                           active: panel == .settings, help: "Settings") {
                toggle(.settings)
            }

            Spacer()
        }
        // Clears the traffic lights, which now sit over the rail.
        .padding(.top, 46)
        .padding(.bottom, 10)
        .frame(width: GeoTheme.railWidth)
        .frame(maxHeight: .infinity)
        .background(GeoTheme.rail)
        // The rail's fill has to reach the literal top edge of the window, not
        // just the safe area below the traffic lights — otherwise the window's
        // own titlebar background shows through as a seam right behind them.
        .ignoresSafeArea(edges: .top)
        .overlay(alignment: .trailing) {
            Rectangle().fill(GeoTheme.border).frame(width: 1)
        }
    }

    private func toggle(_ target: RailPanel) {
        panel = (panel == target) ? nil : target
    }
}

/// Local `ollama serve` needs no credentials at all — this only matters once
/// you point Geocentric at ollama.com's hosted cloud models (or any other
/// remotely-hosted Ollama sitting behind a bearer token).
private struct OllamaAPIKeyField: View {
    @ObservedObject var state: AppState
    @State private var draft: String = ""
    @State private var saved = false

    private var usingCloud: Bool { state.ollamaHost.contains("ollama.com") }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Ollama").font(GeoTheme.ui(11, .medium)).foregroundStyle(GeoTheme.inkSecondary)
                Text(usingCloud ? "Using Ollama Cloud (ollama.com)" : "Using a local Ollama at \(state.ollamaHost.isEmpty ? "localhost:11434" : state.ollamaHost)")
                    .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                HStack(spacing: 6) {
                    Button("Local") { state.useLocalOllama() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .disabled(!usingCloud)
                    Button("Ollama Cloud") { state.useOllamaCloud() }
                        .buttonStyle(.bordered).controlSize(.small)
                        .disabled(usingCloud)
                }
            }

            if usingCloud {
                VStack(alignment: .leading, spacing: 5) {
                    Text("API key").font(GeoTheme.ui(10.5, .medium)).foregroundStyle(GeoTheme.inkSecondary)
                    Text("from your account at ollama.com/settings/keys")
                        .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                    HStack(spacing: 6) {
                        SecureField(state.hasOllamaApiKey ? "••••••••" : "none set", text: $draft)
                            .textFieldStyle(.roundedBorder)
                            .font(GeoTheme.mono(11))
                        Button(saved ? "Saved" : "Save") {
                            state.setOllamaApiKey(draft)
                            draft = ""
                            saved = true
                            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { saved = false }
                        }
                        .font(GeoTheme.ui(10.5, .medium))
                        .disabled(draft.isEmpty && !state.hasOllamaApiKey)
                    }
                }
            }
        }
    }
}

enum RailPanel: String, Identifiable {
    case sessions, tools, machines, settings
    var id: String { rawValue }
    var title: String {
        switch self {
        case .sessions: return "Sessions"
        case .tools: return "Tools"
        case .machines: return "Machines"
        case .settings: return "Settings"
        }
    }
}

/// The expandable drawer that sits between the rail and the main surface.
struct RailDrawerView: View {
    @ObservedObject var state: AppState
    let panel: RailPanel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(panel.title)
                .font(GeoTheme.ui(11, .semibold))
                .foregroundStyle(GeoTheme.inkSecondary)
                .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 9)

            switch panel {
            case .sessions: sessionList
            case .tools: toolList
            case .machines: machinesPanel
            case .settings: settings
            }

            Spacer(minLength: 0)
        }
        .frame(width: 244)
        .frame(maxHeight: .infinity)
        .background(GeoTheme.canvasWarm)
        .overlay(alignment: .trailing) { Rectangle().fill(GeoTheme.border).frame(width: 1) }
    }

    private var sessionList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 3) {
                if state.sessions.isEmpty {
                    Text("No saved sessions yet.")
                        .font(GeoTheme.ui(11.5)).foregroundStyle(GeoTheme.inkTertiary)
                        .padding(.horizontal, 14)
                }
                ForEach(state.sessions) { s in
                    Button { state.resumeSession(s.id) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(s.title.isEmpty ? "(no prompt)" : s.title)
                                .font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.ink)
                                .lineLimit(2).multilineTextAlignment(.leading)
                            Text("\(s.age) · \(s.turns) turns")
                                .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 9).padding(.vertical, 7)
                        .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(GeoTheme.border, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10)
        }
        .onAppear { state.refreshSessions() }
    }

    private var toolList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(["read", "edit", "shell", "git", "web", "peer", "task", "general"], id: \.self) { group in
                    let tools = state.availableTools.filter { $0.group == group }
                    if !tools.isEmpty {
                        Text(group.uppercased())
                            .font(GeoTheme.ui(9, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                            .padding(.top, 4)
                        ForEach(tools) { t in
                            HStack(spacing: 5) {
                                Text(t.name).font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.ink)
                                if t.mutating {
                                    Circle()
                                        .fill(t.danger == "high" ? GeoTheme.danger : GeoTheme.warn)
                                        .frame(width: 4, height: 4)
                                }
                                Spacer()
                            }
                        }
                    }
                }
            }
            .padding(.horizontal, 14)
        }
    }

    private var machinesPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Combine this Mac with another one on the same WiFi — no separate app "
                     + "to install, the other Mac just needs Geocentric running too.")
                    .font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                if let incoming = state.clusterIncomingRequest {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("\(incoming.name) wants to pair").font(GeoTheme.ui(12, .semibold))
                        HStack(spacing: 8) {
                            Button("Accept") { state.answerPairing(accept: true) }
                                .buttonStyle(.borderedProminent).controlSize(.small)
                            Button("Decline") { state.answerPairing(accept: false) }
                                .buttonStyle(.bordered).controlSize(.small)
                        }
                    }
                    .padding(10)
                    .background(GeoTheme.accentWash, in: RoundedRectangle(cornerRadius: 8))
                }

                if let paired = state.clusterPairedPeer {
                    pairedSection(paired)
                } else {
                    linkingSection
                }

                if !state.clusterError.isEmpty {
                    Text(state.clusterError)
                        .font(GeoTheme.ui(10.5)).foregroundStyle(GeoTheme.danger)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.horizontal, 14).padding(.bottom, 14)
        }
    }

    private var linkingSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button(state.clusterLinking ? "Stop linking" : "Link this Mac") {
                state.clusterLinking ? state.stopLinking() : state.startLinking()
            }
            .buttonStyle(.borderedProminent).controlSize(.small)

            if state.clusterLinking {
                if state.clusterPeers.isEmpty {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small).scaleEffect(0.7)
                        Text("Looking for other Macs…").font(GeoTheme.ui(11)).foregroundStyle(GeoTheme.inkTertiary)
                    }
                } else {
                    ForEach(state.clusterPeers) { peer in
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(peer.name).font(GeoTheme.ui(12, .medium)).foregroundStyle(GeoTheme.ink)
                                Text(peer.address).font(GeoTheme.mono(10)).foregroundStyle(GeoTheme.inkTertiary)
                            }
                            Spacer()
                            Button("Pair") { state.requestPairing(peer) }
                                .buttonStyle(.bordered).controlSize(.small)
                        }
                        .padding(8)
                        .background(GeoTheme.card, in: RoundedRectangle(cornerRadius: 7))
                        .overlay(RoundedRectangle(cornerRadius: 7).stroke(GeoTheme.border, lineWidth: 1))
                    }
                }
            }
        }
    }

    private func pairedSection(_ peer: ClusterPeer) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Circle().fill(GeoTheme.success).frame(width: 6, height: 6)
                Text("Paired with \(peer.name)").font(GeoTheme.ui(12, .semibold))
            }

            VStack(alignment: .leading, spacing: 6) {
                ForEach([ClusterMode.cluster, .orchestration], id: \.self) { mode in
                    Button {
                        state.setClusterMode(state.clusterMode == mode ? nil : mode)
                    } label: {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: state.clusterMode == mode ? "largecircle.fill.circle" : "circle")
                                .foregroundStyle(state.clusterMode == mode ? GeoTheme.accent : GeoTheme.inkTertiary)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(mode.title).font(GeoTheme.ui(12, .medium)).foregroundStyle(GeoTheme.ink)
                                Text(mode.subtitle).font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
            }

            Button("Unlink", role: .destructive) { state.stopLinking() }
                .buttonStyle(.bordered).controlSize(.small)
        }
    }

    private var settings: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Effort").font(GeoTheme.ui(11, .medium)).foregroundStyle(GeoTheme.inkSecondary)
                Picker("", selection: Binding(get: { state.effort }, set: { state.setEffort($0) })) {
                    ForEach(["low", "medium", "high", "xhigh", "max", "ultracode"], id: \.self) {
                        Text($0).tag($0)
                    }
                }
                .labelsHidden()
                .font(GeoTheme.ui(11))
            }

            Toggle(isOn: Binding(get: { state.yolo }, set: { state.setYolo($0) })) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Auto-accept").font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.ink)
                    Text("destructive commands still ask")
                        .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                }
            }
            .toggleStyle(.switch)
            .controlSize(.small)

            Divider().overlay(GeoTheme.border)

            OllamaAPIKeyField(state: state)

            Divider().overlay(GeoTheme.border)

            VStack(alignment: .leading, spacing: 10) {
                Text("Geo").font(GeoTheme.ui(11, .medium)).foregroundStyle(GeoTheme.inkSecondary)

                Toggle(isOn: $state.mascotVisible) {
                    Text("Show Geo").font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.ink)
                }
                .toggleStyle(.switch).controlSize(.small)

                Toggle(isOn: $state.mascotAlwaysVisible) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Never hide him").font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.ink)
                        Text("idle animation when nothing's happening")
                            .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                    }
                }
                .toggleStyle(.switch).controlSize(.small)
                .disabled(!state.mascotVisible)

                Toggle(isOn: $state.mascotFloating) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Float over every window").font(GeoTheme.ui(12)).foregroundStyle(GeoTheme.ink)
                        Text("detaches him into his own floating window")
                            .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                    }
                }
                .toggleStyle(.switch).controlSize(.small)
                .disabled(!state.mascotVisible)
            }

            if state.contextWindow > 0 {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Context").font(GeoTheme.ui(11, .medium)).foregroundStyle(GeoTheme.inkSecondary)
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(GeoTheme.sunken)
                            Capsule().fill(GeoTheme.accent)
                                .frame(width: geo.size.width * min(Double(state.contextPercent) / 100, 1))
                        }
                    }
                    .frame(height: 4)
                    Text("\(state.contextUsed) / \(state.contextWindow) tokens")
                        .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                }
            }

            Divider().overlay(GeoTheme.border)

            VStack(alignment: .leading, spacing: 3) {
                Text("Engine").font(GeoTheme.ui(11, .medium)).foregroundStyle(GeoTheme.inkSecondary)
                Text(state.currentModel).font(GeoTheme.mono(10.5)).foregroundStyle(GeoTheme.ink)
                Text(state.projectRoot)
                    .font(GeoTheme.ui(10)).foregroundStyle(GeoTheme.inkTertiary)
                    .lineLimit(2).truncationMode(.head)
            }
        }
        .padding(.horizontal, 14)
    }
}
