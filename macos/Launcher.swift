import AppKit
import WebKit
import UniformTypeIdentifiers

final class TradeRoom: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var child: Process?
    var parentPipe: Pipe?
    var origin: URL?
    var quitting = false
    var ready = false
    let output = Pipe()
    var buffer = Data()
    var bundledResources: URL {
        URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
            .deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Resources", isDirectory: true)
    }
    var verificationDirectory: URL? {
        guard CommandLine.arguments.contains("--offline-verification"),
              CommandLine.arguments.contains("--verify-ui"),
              let index = CommandLine.arguments.firstIndex(of: "--verification-home"),
              CommandLine.arguments.count > index + 1 else { return nil }
        return URL(fileURLWithPath: CommandLine.arguments[index + 1], isDirectory: true)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.appearance = NSAppearance(named: .darkAqua)
        let menu = NSMenu()
        let item = NSMenuItem(); menu.addItem(item)
        let application = NSMenu(); item.submenu = application
        application.addItem(withTitle: "About Trade Room", action: #selector(about), keyEquivalent: "")
        application.addItem(withTitle: "Local Setup…", action: #selector(setup), keyEquivalent: ",")
        application.addItem(.separator())
        application.addItem(withTitle: "Quit Trade Room", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem(); menu.addItem(editItem)
        let edit = NSMenu(title: "Edit"); editItem.submenu = edit
        for (title, selector, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1200, height: 850),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Trade Room"; window.minSize = NSSize(width: 800, height: 600)
        window.delegate = self; window.center()
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController.add(self, name: "lifecycle")
        if verificationDirectory != nil { config.userContentController.add(self, name: "verification") }
        web = WKWebView(frame: window.contentView!.bounds, configuration: config)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self; web.uiDelegate = self
        window.contentView = web
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        web.loadHTMLString("<html><body style='background:#090f17;color:#e1ebed;font:18px -apple-system;padding:64px'><h1>Trade Room</h1><p>Starting your local synthetic demo…</p><p>AI is off. No ESPN connection is made.</p></body></html>", baseURL: nil)
        if verificationDirectory != nil {
            DispatchQueue.global().async { [weak self] in
                let data = FileHandle.standardInput.readDataToEndOfFile()
                DispatchQueue.main.async {
                    if String(data: data, encoding: .utf8) == "close\n" { self?.window.performClose(nil) }
                    else { NSApp.terminate(nil) }
                }
            }
        }
        startBackend()
    }
    @objc func about() {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        let alert = NSAlert(); alert.messageText = "Trade Room \(version)"
        alert.informativeText = "Read-only fantasy trade workbench. Apple Silicon · macOS 13+. Bundled Python and Pillow; on-device English OCR via Apple Vision. AI is always off in the desktop app. Unsigned and not notarized."
        alert.runModal()
    }
    @objc func setup() { web.evaluateJavaScript("document.querySelector('#desktop-setup')?.click()", completionHandler: nil) }
    func startBackend() {
        let resources = bundledResources
        let process = Process()
        process.executableURL = resources.appendingPathComponent("python/bin/python3")
        process.arguments = ["-I", "-B", resources.appendingPathComponent("backend/desktop_entry.py").path]
        if CommandLine.arguments.contains("--offline-verification") { process.arguments?.append("--offline-verification") }
        // Deliberate allowlist: no shell, user Python, proxy, ESPN, LLM or DYLD settings.
        var supportHome = NSHomeDirectory()
        // Synthetic verification can use a fresh home without reading personal settings.
        if let index = CommandLine.arguments.firstIndex(of: "--verification-home"), CommandLine.arguments.count > index + 1 {
            supportHome = CommandLine.arguments[index + 1]
        }
        process.environment = ["HOME": supportHome, "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8", "TMPDIR": NSTemporaryDirectory()]
        process.currentDirectoryURL = resources
        parentPipe = Pipe(); process.standardInput = parentPipe
        process.standardOutput = output; process.standardError = FileHandle.nullDevice
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            DispatchQueue.main.async { self?.receive(data) }
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { if let self = self, !self.quitting { self.failure() } }
        }
        child = process
        do { try process.run() } catch { failure(); return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 25) { [weak self] in
            guard let self = self, !self.ready, !self.quitting else { return }
            self.failure()
        }
    }
    func receive(_ data: Data) {
        guard !ready, !quitting else { return }
        buffer.append(data)
        guard buffer.count <= 4096 else { failure(); return }
        guard buffer.contains(10) else { return }
        guard let value = try? JSONSerialization.jsonObject(with: buffer) as? [String: String],
              let raw = value["url"], let url = URL(string: raw), url.scheme == "http",
              url.host == "127.0.0.1", url.port != nil, url.path == "/" else { failure(); return }
        ready = true; origin = url
        web.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
    }
    func failure() {
        guard !quitting else { return }
        if let directory = verificationDirectory {
            let status = child?.isRunning == false ? child?.terminationStatus ?? -1 : -1
            let result: [String: Any] = ["stage":"final", "ok":false, "error":"Native startup failed", "backend_exit_status":status]
            if let data = try? JSONSerialization.data(withJSONObject: result) {
                try? data.write(to: directory.appendingPathComponent("ui-result.json"), options: .atomic)
            }
            NSApp.terminate(nil)
            return
        }
        let alert = NSAlert(); alert.messageText = "Trade Room could not start"
        alert.informativeText = "Quit and reopen the complete app from Applications. It needs an Apple Silicon Mac with macOS 13 or newer. Keep the app’s Contents intact. Check that ~/Library/Application Support/Trade Room is owned by you and uses ordinary files (no links). No settings or credentials were logged."
        alert.addButton(withTitle: "Quit"); alert.runModal()
        NSApp.terminate(nil)
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.absoluteString == "about:blank" { decisionHandler(.allow); return }
        let local = url.scheme == origin?.scheme && url.host == origin?.host && url.port == origin?.port
        decisionHandler(local ? .allow : .cancel)
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.png, .jpeg]
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard let directory = verificationDirectory, webView.url?.host == "127.0.0.1",
              let fixture = try? Data(contentsOf: directory.appendingPathComponent("synthetic-roster.png")),
              let script = try? String(contentsOf: bundledResources.appendingPathComponent("verify_ui.js"), encoding: .utf8) else { return }
        web.evaluateJavaScript(script.replacingOccurrences(of: "__SYNTHETIC_PNG__", with: fixture.base64EncodedString()), completionHandler: nil)
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "verification", let directory = verificationDirectory,
           message.frameInfo.isMainFrame, message.frameInfo.securityOrigin.host == "127.0.0.1",
           let data = try? JSONSerialization.data(withJSONObject: message.body, options: [.prettyPrinted, .sortedKeys]) {
            let body = message.body as? [String: Any] ?? [:]
            let capture = body["capture"] as? Int ?? 0
            let stage = body["stage"] as? String ?? "final"
            let complete = { self.web.evaluateJavaScript("window.__verificationComplete?.(\(capture))", completionHandler: nil) }
            if stage == "resize", let width = body["width"] as? Int, let height = body["height"] as? Int,
               (800...1600).contains(width), (600...1200).contains(height) {
                // Frame size, including title bar: test the actual minimum window.
                var frame = window.frame; frame.size = NSSize(width: width, height: height)
                window.setFrame(frame, display: true)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: complete)
                return
            }
            try? data.write(to: directory.appendingPathComponent("ui-result.json"), options: .atomic)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                self.web.takeSnapshot(with: nil) { image, _ in
                    if let tiff = image?.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
                       let png = bitmap.representation(using: .png, properties: [:]),
                       stage.range(of: "^(welcome|ocr|setup|final)(-[a-z0-9-]+)?$", options: .regularExpression) != nil {
                        try? png.write(to: directory.appendingPathComponent("ui-\(stage).png"), options: .atomic)
                    }
                    complete()
                }
            }
            return
        }
        guard message.name == "lifecycle", message.frameInfo.isMainFrame,
              message.frameInfo.securityOrigin.protocol == "http",
              message.frameInfo.securityOrigin.host == "127.0.0.1",
              message.frameInfo.securityOrigin.port == origin?.port else { return }
        if message.body as? String == "quit" { NSApp.terminate(nil); return }
        if let body = message.body as? [String: String], body["action"] == "open-release",
           let raw = body["url"], let url = URL(string: raw),
           let data = try? Data(contentsOf: bundledResources.appendingPathComponent("backend/release.json")),
           let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let repo = config["repository"] as? String,
           repo.range(of: "^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$", options: .regularExpression) != nil {
            let prefix = "https://github.com/\(repo)/releases/tag/v"
            if raw.hasPrefix(prefix), String(raw.dropFirst(prefix.count)).range(of: "^[1-9][0-9]{0,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$", options: .regularExpression) != nil {
                NSWorkspace.shared.open(url)
            }
        }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { NSApp.terminate(nil); return false }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        quitting = true
        output.fileHandleForReading.readabilityHandler = nil
        try? parentPipe?.fileHandleForWriting.close()
        if let process = child, process.isRunning {
            kill(-process.processIdentifier, SIGTERM)
            process.terminate()
            let deadline = Date().addingTimeInterval(3)
            while process.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if process.isRunning { kill(process.processIdentifier, SIGKILL) }
            kill(-process.processIdentifier, SIGKILL)
            process.waitUntilExit()
            if let directory = verificationDirectory,
               let result = try? JSONSerialization.data(withJSONObject: ["backend_exit_status":process.terminationStatus, "backend_alive":process.isRunning]) {
                try? result.write(to: directory.appendingPathComponent("stop-result.json"), options: .atomic)
            }
        }
    }
}
let app = NSApplication.shared
let delegate = TradeRoom()
app.delegate = delegate
app.run()
