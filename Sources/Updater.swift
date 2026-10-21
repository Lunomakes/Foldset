import SwiftUI
import AppKit
import CryptoKit

/// Checks GitHub Releases for a newer build, downloads and verifies it, then swaps it in and relaunches.
/// Nothing touches the installed app until the package has passed its checksum and signature checks;
/// the swap itself runs in a helper after we quit and restores the old app if any step fails.
@MainActor final class Updater: ObservableObject {
    static let shared = Updater()
    static let autoCheckKey = "autoCheckUpdates"
    nonisolated static let repo = URL(string: "https://github.com/Lunomakes/Foldset/releases")!
    /// Redirects to releases/tag/<tag>. Unlike api.github.com it has no 60-requests-per-hour limit per IP.
    static let feed = repo.appendingPathComponent("latest")
    /// Written by the install helper when the swap failed, so the next launch can say so.
    static let failureMarker = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        .appendingPathComponent(Bundle.main.bundleIdentifier ?? "Foldset").appendingPathComponent("update-failed")

    struct Release: Equatable {
        let version: String
        let zip: URL
        let checksum: URL
    }
    enum Phase: Equatable {
        case idle, checking, upToDate
        case available(Release)
        case downloading(Double)
        case installing
        case failed(String)
    }
    enum UpdateError: Error { case server, corrupt, notWritable }

    @Published private(set) var phase = Phase.idle
    /// The newer release last found, if any; drives the sidebar badge.
    @Published private(set) var latest: Release?
    let current = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
    /// Set while a download is in flight, so Retry downloads again instead of re-checking.
    private var pending: Release?

    var busy: Bool {
        switch phase {
        case .checking, .downloading, .installing: true
        default: false
        }
    }

    /// `quietly` (the launch check) leaves the visible status alone unless a newer release turns up.
    func check(quietly: Bool = false) async {
        guard !busy else { return }
        let before = phase
        phase = .checking
        pending = nil
        do {
            var request = URLRequest(url: Self.feed, timeoutInterval: 15)
            request.httpMethod = "HEAD"
            let (_, response) = try await URLSession.shared.data(for: request)
            guard (response as? HTTPURLResponse)?.statusCode == 200, let final = response.url,
                  let release = Self.release(fromTagURL: final) else { throw UpdateError.server }
            let newer = AppVersion.isNewer(release.version, than: current)
            latest = newer ? release : nil
            phase = newer ? .available(release) : quietly ? before : .upToDate
        } catch {
            phase = quietly ? before : .failed(Self.message(for: error, downloading: false))
        }
    }

    func install(_ release: Release) async {
        guard !busy else { return }
        pending = release
        phase = .downloading(0)
        let fm = FileManager.default
        let work = fm.temporaryDirectory.appendingPathComponent("FoldsetUpdate-\(UUID().uuidString)")
        do {
            let destination = Bundle.main.bundleURL
            guard fm.isWritableFile(atPath: destination.deletingLastPathComponent().path) else { throw UpdateError.notWritable }
            try fm.createDirectory(at: work, withIntermediateDirectories: true)
            let (sum, sumResponse) = try await URLSession.shared.data(from: release.checksum)
            guard (sumResponse as? HTTPURLResponse)?.statusCode == 200,
                  let expected = String(decoding: sum, as: UTF8.self).split(separator: " ").first.map({ $0.lowercased() }),
                  expected.count == 64 else { throw UpdateError.server }
            let zip = work.appendingPathComponent("update.zip")
            // The async download(from:delegate:) API never reports progress, so observe a classic task instead.
            var observation: NSKeyValueObservation?
            defer { observation?.invalidate() }
            let response: URLResponse = try await withCheckedThrowingContinuation { continuation in
                let task = URLSession.shared.downloadTask(with: release.zip) { url, response, error in
                    guard let url, let response else { return continuation.resume(throwing: error ?? URLError(.unknown)) }
                    // The temporary file is deleted when this handler returns.
                    do { try FileManager.default.moveItem(at: url, to: zip); continuation.resume(returning: response) }
                    catch { continuation.resume(throwing: error) }
                }
                observation = task.progress.observe(\.fractionCompleted) { [weak self] progress, _ in
                    let fraction = progress.fractionCompleted
                    Task { @MainActor in
                        if case .downloading(let shown) = self?.phase, fraction - shown >= 0.01 || fraction == 1 { self?.phase = .downloading(fraction) }
                    }
                }
                task.resume()
            }
            guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw UpdateError.server }
            phase = .installing
            let app = try await Task.detached { try Self.unpack(zip, expected: expected, into: work) }.value
            try Self.launchSwap(new: app, replacing: destination, work: work)
            NSApp.terminate(nil)
        } catch {
            try? fm.removeItem(at: work)
            phase = .failed(Self.message(for: error, downloading: true))
        }
    }

    func retry() {
        Task {
            if let pending { await install(pending) } else { await check() }
        }
    }

    /// Builds asset URLs from ".../releases/tag/v1.2.3", matching the names scripts/package.sh uploads.
    nonisolated static func release(fromTagURL url: URL) -> Release? {
        let tag = url.lastPathComponent
        guard url.deletingLastPathComponent().lastPathComponent == "tag", tag.first == "v" else { return nil }
        let version = String(tag.dropFirst())
        let zip = repo.appendingPathComponent("download/\(tag)/Foldset-\(version)-arm64.zip")
        return Release(version: version, zip: zip, checksum: zip.appendingPathExtension("sha256"))
    }

    /// Verifies the zip's SHA-256, extracts it and checks the app inside; returns the extracted app.
    nonisolated private static func unpack(_ zip: URL, expected: String, into work: URL) throws -> URL {
        let digest = SHA256.hash(data: try Data(contentsOf: zip, options: .mappedIfSafe)).map { String(format: "%02x", $0) }.joined()
        guard digest == expected else { throw UpdateError.corrupt }
        let unpacked = work.appendingPathComponent("unpacked")
        try run("/usr/bin/ditto", "-x", "-k", zip.path, unpacked.path)
        guard let app = try FileManager.default.contentsOfDirectory(at: unpacked, includingPropertiesForKeys: nil).first(where: { $0.pathExtension == "app" }),
              Bundle(url: app)?.bundleIdentifier == Bundle.main.bundleIdentifier else { throw UpdateError.corrupt }
        try run("/usr/bin/codesign", "--verify", "--deep", "--strict", app.path)
        return app
    }

    nonisolated private static func run(_ tool: String, _ arguments: String...) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: tool)
        process.arguments = arguments
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw UpdateError.corrupt }
    }

    /// Starts a helper that waits for us to quit, swaps the bundles (restoring the old one on failure) and relaunches.
    private static func launchSwap(new: URL, replacing destination: URL, work: URL) throws {
        let script = work.appendingPathComponent("swap.zsh")
        try """
        pid=$1 new=$2 dst=$3 work=$4 marker=$5 ok=0
        while kill -0 $pid 2>/dev/null; do sleep 0.2; done
        if mv "$dst" "$work/previous.app"; then
            if ditto "$new" "$dst" && codesign --verify --deep --strict "$dst"; then ok=1
            else rm -rf "$dst"; mv "$work/previous.app" "$dst"; fi
        fi
        (( ok )) || { mkdir -p "${marker:h}"; touch "$marker"; }
        open "$dst"
        # Keep the work folder if the restore failed: it holds the only copy of the previous app.
        [[ -d "$dst" ]] && rm -rf "$work"
        """.write(to: script, atomically: true, encoding: .utf8)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = [script.path, String(ProcessInfo.processInfo.processIdentifier), new.path, destination.path, work.path, failureMarker.path]
        try process.run()
    }

    nonisolated static func message(for error: Error, downloading: Bool) -> String {
        let offline: [URLError.Code] = [.notConnectedToInternet, .networkConnectionLost, .timedOut, .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed]
        switch error {
        case UpdateError.corrupt: return "更新包校验失败，可能已损坏。当前版本未受影响，请重试。"
        case UpdateError.notWritable: return "无法替换当前 App。请将 Foldset 移到“应用程序”文件夹后重试，或前往 GitHub 手动下载。"
        case UpdateError.server: return "更新服务暂时不可用，请稍后重试。"
        case let error as URLError where offline.contains(error.code):
            return downloading ? "下载中断，请检查网络后重试。当前版本未受影响。" : "无法连接更新服务器，请检查网络后重试。"
        default: return downloading ? "下载更新失败，当前版本未受影响。请重试。" : "检查更新失败，请稍后重试。"
        }
    }
}

/// Small static label shown only while a newer release is known; opens the update details on click.
struct UpdateBadge: View {
    @ObservedObject var updater: Updater
    @ViewState private var showDetails = false
    var body: some View {
        if let release = updater.latest {
            Button { showDetails = true } label: {
                Text("新版本").font(.caption2.weight(.medium)).foregroundStyle(Theme.ink2)
                    .padding(.horizontal, 6).padding(.vertical, 1)
                    .overlay(Capsule().strokeBorder(Theme.border))
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .help("Foldset \(release.version) 可用")
            .accessibilityLabel("Foldset \(release.version) 可用，查看更新")
            .popover(isPresented: $showDetails, arrowEdge: .bottom) {
                Form { Section("软件更新") { UpdateStatusView(updater: updater) } }
                    .formStyle(.grouped).scrollDisabled(true).frame(width: 380).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// Status, progress and actions for the update flow; used in Settings and the sidebar badge's popover.
struct UpdateStatusView: View {
    @ObservedObject var updater: Updater
    var body: some View {
        switch updater.phase {
        case .idle, .upToDate:
            LabeledContent(updater.phase == .upToDate ? "已是最新版本" : "当前版本 \(updater.current)") {
                Button("检查更新") { Task { await updater.check() } }
            }
        case .checking:
            LabeledContent("正在检查更新…") { ProgressView().controlSize(.small) }
        case .available(let release):
            LabeledContent("发现新版本 \(release.version)（当前 \(updater.current)）") {
                Button("立即更新") { Task { await updater.install(release) } }.buttonStyle(.borderedProminent)
            }
        case .downloading(let fraction):
            ProgressView(value: fraction) { Text("正在下载更新…") }
                currentValueLabel: { Text(fraction.formatted(.percent.precision(.fractionLength(0)))) }
        case .installing:
            LabeledContent("正在校验并安装，完成后将自动重启…") { ProgressView().controlSize(.small) }
        case .failed(let message):
            LabeledContent {
                Button("重试") { updater.retry() }
            } label: {
                Label(message, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
        }
    }
}
