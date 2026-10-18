import SwiftUI
import AppKit

struct ResolveExtensionView: View {
    @ObservedObject var store: TemplateStore
    @ViewState private var state: ResolveExtension.State = .absent
    @ViewState private var bundledVersion = "—"
    @ViewState private var resolveDetected = false
    @ViewState private var busy = false
    @ViewState private var confirmUninstall = false
    @ViewState private var message: String?
    @ViewState private var packageError: String?
    @Environment(\.scenePhase) private var scenePhase
    private var installer: ResolveExtension {
        ResolveExtension(payload: Bundle.main.resourceURL!.appendingPathComponent("ResolveExtension"))
    }
    private var isPreview: Bool {
        #if NATIVE_PREVIEW
        return true
        #else
        return false
        #endif
    }
    private var resolveRunning: Bool {
        NSWorkspace.shared.runningApplications.contains { ($0.bundleIdentifier ?? "").hasPrefix("com.blackmagic-design.DaVinciResolve") || $0.localizedName == "DaVinci Resolve" }
    }
    var body: some View {
        Form {
            Section {
                Text("在达芬奇中按模板创建媒体夹，扫描与整理项目素材。")
                    .foregroundStyle(.secondary)
                LabeledContent("Resolve", value: resolveDetected ? "已检测到" : "未检测到（仍可安装扩展）")
                LabeledContent("扩展", value: state.label)
                LabeledContent("随 App 提供", value: bundledVersion)
                HStack {
                    Button(actionTitle) { perform(uninstall: false) }
                        .disabled(isPreview || busy || packageError != nil || store.persistenceError != nil)
                    Button("检查安装") { refresh(); message = "已检查程序文件、版本和模板菜单；实际运行请在 Resolve 中验证。" }
                        .disabled(busy)
                    if state != .absent {
                        Button("卸载…", role: .destructive) { confirmUninstall = true }.disabled(isPreview || busy)
                    }
                    if busy { ProgressView().controlSize(.small) }
                }
                #if NATIVE_PREVIEW
                Text("预览版仅展示状态，请使用正式版安装或卸载。").font(.caption).foregroundStyle(.secondary)
                #endif
            } header: { Text("DaVinci Resolve") }
            footer: {
                Text("仅安装到当前用户。更新或卸载前，请退出 Resolve。卸载保留模板、操作日志和项目备份。")
            }
            Section {
                Text("菜单位置：工作区 → 脚本 → Foldset")
                Text("安装后重新打开 Resolve。已验证 Studio 21.1；免费版和其他版本尚未验证。")
                    .font(.caption).foregroundStyle(.secondary)
                if let packageError { Text(packageError).foregroundStyle(.orange) }
                if let message { Text(message).font(.callout).textSelection(.enabled) }
            }
        }
        .onAppear { refresh() }
        .onChange(of: scenePhase) { _, phase in if phase == .active { refresh() } }
        .confirmationDialog("卸载 Resolve 扩展？", isPresented: $confirmUninstall) {
            Button("卸载扩展", role: .destructive) { perform(uninstall: true) }
        } message: {
            Text("仅将 Foldset 扩展程序和受管理的菜单移入安装备份。模板、操作日志、项目备份和其他脚本全部保留。")
        }
    }
    private var actionTitle: String {
        switch state {
        case .absent: return "安装扩展"
        case .installed: return "重新安装"
        case .update: return "更新扩展"
        case .incomplete: return "修复安装"
        }
    }
    private func refresh() {
        let workspace = NSWorkspace.shared
        resolveDetected = resolveRunning || ["com.blackmagic-design.DaVinciResolve", "com.blackmagic-design.DaVinciResolveStudio", "com.blackmagic-design.DaVinciResolveLite"].contains { workspace.urlForApplication(withBundleIdentifier: $0) != nil }
            || FileManager.default.fileExists(atPath: "/Applications/DaVinci Resolve/DaVinci Resolve.app")
        do { bundledVersion = try installer.bundledManifest().version; packageError = nil }
        catch { packageError = error.localizedDescription }
        state = installer.state(templates: store.templates)
    }
    private func perform(uninstall: Bool) {
        #if NATIVE_PREVIEW
        message = "预览版不修改真实扩展，请使用正式版。"
        #else
        guard !resolveRunning else { message = "请先退出 DaVinci Resolve，再进行安装、更新或卸载。"; return }
        busy = true
        message = nil
        // Serialize with the store's main-queue menu synchronization.
        DispatchQueue.main.async {
            defer { busy = false; refresh() }
            do {
                if uninstall { try installer.uninstall() }
                else { try installer.install(templates: store.prepareResolveTemplates()) }
                message = uninstall ? "扩展已卸载，用户数据与程序备份已保留。" : "扩展已安装。请打开 Resolve，从工作区 → 脚本 → Foldset 使用。"
            } catch { message = error.localizedDescription }
        }
        #endif
    }
}
