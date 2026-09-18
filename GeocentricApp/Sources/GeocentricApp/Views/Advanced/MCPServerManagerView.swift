import SwiftUI

struct MCPServerConfig: Identifiable, Equatable {
    var id: UUID = UUID()
    var name: String
    var type: String // stdio, sse
    var commandOrURL: String
    var isConnected: Bool = true
}

struct MCPServerManagerView: View {
    @Binding var isPresented: Bool
    @State private var servers: [MCPServerConfig] = [
        MCPServerConfig(name: "FileSystem Server", type: "stdio", commandOrURL: "npx -y @modelcontextprotocol/server-filesystem .", isConnected: true),
        MCPServerConfig(name: "PostgreSQL Database", type: "stdio", commandOrURL: "npx -y @modelcontextprotocol/server-postgres postgresql://localhost/dev", isConnected: false),
        MCPServerConfig(name: "Fetch Web Tool", type: "sse", commandOrURL: "http://localhost:8080/sse", isConnected: true)
    ]
    @State private var newName: String = ""
    @State private var newCommand: String = ""
    @State private var newType: String = "stdio"

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "cpu")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(GeoTheme.accent)
                    Text("MCP Server Manager")
                        .font(GeoTheme.serif(20))
                }
                Spacer()
                Button {
                    isPresented = false
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 18))
                        .foregroundStyle(GeoTheme.inkTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(18)
            .background(GeoTheme.canvasWarm)
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Model Context Protocol (MCP)")
                            .font(GeoTheme.ui(14, .bold))
                        Text("Connect external tools, databases, and context servers directly to Geocentric local AI engine.")
                            .font(GeoTheme.ui(12))
                            .foregroundStyle(GeoTheme.inkSecondary)
                    }

                    // Server list
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Active Servers").font(GeoTheme.ui(12, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                        ForEach(servers) { server in
                            HStack(spacing: 12) {
                                Circle()
                                    .fill(server.isConnected ? GeoTheme.success : GeoTheme.inkTertiary)
                                    .frame(width: 8, height: 8)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(server.name).font(GeoTheme.ui(13, .semibold))
                                    Text(server.commandOrURL).font(GeoTheme.mono(11)).foregroundStyle(GeoTheme.inkSecondary)
                                }
                                Spacer()
                                Text(server.type.uppercased())
                                    .font(GeoTheme.mono(10, .bold))
                                    .padding(.horizontal, 7).padding(.vertical, 3)
                                    .background(GeoTheme.sunken, in: Capsule())
                            }
                            .padding(12)
                            .background(GeoTheme.card)
                            .cornerRadius(9)
                            .overlay(RoundedRectangle(cornerRadius: 9).stroke(GeoTheme.border, lineWidth: 1))
                        }
                    }

                    // Add new server form
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Add MCP Server").font(GeoTheme.ui(12, .bold)).foregroundStyle(GeoTheme.inkTertiary)
                        VStack(spacing: 10) {
                            TextField("Server Name (e.g., GitHub MCP)", text: $newName)
                                .textFieldStyle(.roundedBorder)
                            TextField("Command or Endpoint (e.g., npx @mcp/server)", text: $newCommand)
                                .textFieldStyle(.roundedBorder)
                            HStack {
                                Picker("Protocol", selection: $newType) {
                                    Text("stdio").tag("stdio")
                                    Text("SSE").tag("sse")
                                }
                                .pickerStyle(.segmented)

                                Spacer()

                                Button("Add Server") {
                                    guard !newName.isEmpty && !newCommand.isEmpty else { return }
                                    servers.append(MCPServerConfig(name: newName, type: newType, commandOrURL: newCommand, isConnected: true))
                                    newName = ""
                                    newCommand = ""
                                }
                                .buttonStyle(WorkActionButton())
                            }
                        }
                        .padding(14)
                        .background(GeoTheme.sunken.opacity(0.5))
                        .cornerRadius(10)
                    }
                }
                .padding(20)
            }
        }
        .frame(width: 520, height: 500)
        .background(GeoTheme.card)
    }
}
