import Foundation
import UIKit
import WebKit
import Capacitor

/// In-app Canvas login → capture authenticated `canvas_session` for StudyFlows.
///
/// Design notes (TAMU / Duo SSO):
/// - Canvas sets an anonymous `canvas_session` before login; never treat cookie presence alone as success.
/// - Duo redirects cancel loads (−999); ignore those.
/// - Verify with a native request to `/api/v1/users/self` using `HTTPCookie.requestHeaderFields`
///   (correct Cookie encoding). Do not rely on page JS `fetch` (CSP / wrong origin while on CAS).
/// - Capture can succeed as soon as the cookie jar has a valid session, even if the visible URL
///   is still settling after SSO.
@objc(CanvasLoginPlugin)
public class CanvasLoginPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "CanvasLoginPlugin"
    public let jsName = "CanvasLogin"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "loginAndCaptureSession", returnType: CAPPluginReturnPromise)
    ]

    @objc func loginAndCaptureSession(_ call: CAPPluginCall) {
        guard let baseUrlRaw = call.getString("baseUrl")?.trimmingCharacters(in: .whitespacesAndNewlines),
              !baseUrlRaw.isEmpty,
              let baseURL = URL(string: baseUrlRaw),
              let host = baseURL.host, !host.isEmpty,
              baseURL.scheme == "https" || baseURL.scheme == "http"
        else {
            call.reject("A valid Canvas baseUrl is required")
            return
        }

        DispatchQueue.main.async { [weak self] in
            guard let self, let presenter = self.bridge?.viewController else {
                call.reject("Unable to present Canvas login")
                return
            }

            let vc = CanvasLoginViewController(baseURL: baseURL) { result in
                switch result {
                case .success(let cookie):
                    call.resolve([
                        "sessionCookie": cookie,
                        "baseUrl": baseUrlRaw
                    ])
                case .cancelled:
                    call.reject("Login cancelled", "CANCELLED")
                case .failure(let message):
                    call.reject(message)
                }
            }

            let nav = UINavigationController(rootViewController: vc)
            nav.modalPresentationStyle = .fullScreen
            presenter.present(nav, animated: true)
        }
    }
}

private enum CanvasLoginResult {
    case success(String)
    case cancelled
    case failure(String)
}

private final class CanvasLoginViewController: UIViewController, WKNavigationDelegate {
    private let baseURL: URL
    private let completion: (CanvasLoginResult) -> Void
    private let dataStore = WKWebsiteDataStore.nonPersistent()
    private var webView: WKWebView!
    private var pollTimer: Timer?
    private var finished = false
    private var verifying = false
    private var verifyStartedAt: Date?
    private var lastStatusCode: Int?
    private var statusLabel: UILabel!

    private let verifyTimeout: TimeInterval = 8
    private let userAgent = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

    init(baseURL: URL, completion: @escaping (CanvasLoginResult) -> Void) {
        self.baseURL = baseURL
        self.completion = completion
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        title = "Sign in to Canvas"

        navigationItem.leftBarButtonItem = UIBarButtonItem(
            barButtonSystemItem: .cancel,
            target: self,
            action: #selector(cancelTapped)
        )

        let reload = UIBarButtonItem(title: "Canvas home", style: .plain, target: self, action: #selector(reloadCanvasHome))
        let done = UIBarButtonItem(title: "I'm signed in", style: .done, target: self, action: #selector(manualContinueTapped))
        navigationItem.rightBarButtonItems = [done, reload]

        statusLabel = UILabel()
        statusLabel.text = "1) Sign in with NetID / Duo below. 2) Wait until you see your Canvas dashboard. 3) Or tap I'm signed in."
        statusLabel.font = .preferredFont(forTextStyle: .footnote)
        statusLabel.textColor = .secondaryLabel
        statusLabel.numberOfLines = 0
        statusLabel.translatesAutoresizingMaskIntoConstraints = false

        let config = WKWebViewConfiguration()
        config.websiteDataStore = dataStore
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        if #available(iOS 14.0, *) {
            config.defaultWebpagePreferences.preferredContentMode = .mobile
        }

        webView = WKWebView(frame: .zero, configuration: config)
        webView.customUserAgent = userAgent
        webView.navigationDelegate = self
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.allowsBackForwardNavigationGestures = true

        view.addSubview(statusLabel)
        view.addSubview(webView)

        NSLayoutConstraint.activate([
            statusLabel.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 8),
            statusLabel.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            statusLabel.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            webView.topAnchor.constraint(equalTo: statusLabel.bottomAnchor, constant: 8),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])

        webView.load(URLRequest(url: baseURL.appendingPathComponent("login")))

        pollTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.attemptCapture(userInitiated: false)
        }
    }

    deinit {
        pollTimer?.invalidate()
    }

    @objc private func cancelTapped() {
        finish(.cancelled)
    }

    @objc private func reloadCanvasHome() {
        statusLabel.text = "Loading Canvas home…"
        webView.load(URLRequest(url: baseURL))
    }

    @objc private func manualContinueTapped() {
        statusLabel.text = "Checking Canvas session…"
        // Force a fresh attempt even if a prior verify hung.
        verifying = false
        verifyStartedAt = nil
        attemptCapture(userInitiated: true)
    }

    private func finish(_ result: CanvasLoginResult) {
        guard !finished else { return }
        finished = true
        pollTimer?.invalidate()
        pollTimer = nil
        dismiss(animated: true) {
            self.completion(result)
        }
    }

    private func resetVerifyIfTimedOut() {
        guard verifying, let started = verifyStartedAt else { return }
        if Date().timeIntervalSince(started) > verifyTimeout {
            verifying = false
            verifyStartedAt = nil
        }
    }

    private func attemptCapture(userInitiated: Bool) {
        guard !finished else { return }
        resetVerifyIfTimedOut()
        guard !verifying else { return }

        dataStore.httpCookieStore.getAllCookies { [weak self] cookies in
            guard let self, !self.finished else { return }

            let relevant = cookies.filter { self.isRelevantCanvasCookie($0) }
            guard relevant.contains(where: { $0.name == "canvas_session" }) else {
                if userInitiated {
                    DispatchQueue.main.async {
                        self.statusLabel.text = "No canvas_session cookie yet. Finish Duo, tap Canvas home, then I'm signed in."
                    }
                }
                return
            }

            let headerFields = HTTPCookie.requestHeaderFields(with: relevant)
            guard let cookieHeader = headerFields["Cookie"], !cookieHeader.isEmpty else {
                if userInitiated {
                    DispatchQueue.main.async {
                        self.statusLabel.text = "Could not build Cookie header. Try Canvas home, then I'm signed in."
                    }
                }
                return
            }

            guard let sessionValue = self.canvasSessionValue(fromCookieHeader: cookieHeader) else {
                if userInitiated {
                    DispatchQueue.main.async {
                        self.statusLabel.text = "canvas_session missing from cookie header. Try again."
                    }
                }
                return
            }

            guard let selfURL = self.usersSelfURL() else {
                DispatchQueue.main.async {
                    self.verifying = false
                    self.verifyStartedAt = nil
                    self.statusLabel.text = "Invalid Canvas base URL."
                }
                return
            }

            self.verifying = true
            self.verifyStartedAt = Date()

            DispatchQueue.main.async {
                if userInitiated || self.lastStatusCode != nil {
                    self.statusLabel.text = "Found session cookie — verifying with Canvas…"
                }
            }

            var request = URLRequest(url: selfURL)
            request.httpMethod = "GET"
            request.timeoutInterval = 15
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.setValue(cookieHeader, forHTTPHeaderField: "Cookie")
            request.setValue(self.userAgent, forHTTPHeaderField: "User-Agent")

            URLSession.shared.dataTask(with: request) { data, response, error in
                DispatchQueue.main.async {
                    self.verifying = false
                    self.verifyStartedAt = nil
                    guard !self.finished else { return }

                    if let error {
                        self.statusLabel.text = "Verify failed: \(error.localizedDescription). Tap I'm signed in to retry."
                        return
                    }

                    let status = (response as? HTTPURLResponse)?.statusCode ?? -1
                    self.lastStatusCode = status

                    guard status == 200, let data else {
                        // Anonymous pre-login cookie → 401. Keep waiting quietly unless user tapped.
                        if userInitiated || status != 401 {
                            self.statusLabel.text = "Canvas says not signed in yet (HTTP \(status)). Finish login, open Canvas home, then I'm signed in."
                        } else {
                            self.statusLabel.text = "Waiting for NetID / Duo to finish…"
                        }
                        return
                    }

                    guard
                        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                        json["id"] != nil
                    else {
                        self.statusLabel.text = "Unexpected Canvas response. Tap I'm signed in to retry."
                        return
                    }

                    let name = (json["name"] as? String).flatMap { $0.isEmpty ? nil : $0 }
                    self.statusLabel.text = name.map { "Signed in as \($0) — connecting…" } ?? "Signed in — connecting…"
                    self.finish(.success(sessionValue))
                }
            }.resume()
        }
    }

    private func usersSelfURL() -> URL? {
        // Do NOT use URL.appendingPathComponent for multi-segment API paths — it can encode "/" as %2F and 404.
        let root = baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return URL(string: "\(root)/api/v1/users/self")
    }

    /// Cookies that belong to the Canvas site (not CAS/Duo IdP cookies).
    private func isRelevantCanvasCookie(_ cookie: HTTPCookie) -> Bool {
        let host = (baseURL.host ?? "").lowercased()
        let domain = cookie.domain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        if host.isEmpty { return false }
        if host == domain || host.hasSuffix("." + domain) || domain.hasSuffix(host) {
            return true
        }
        // Shared Instructure cookie domains used by some Canvas hosts.
        return domain.contains("instructure.com") && host.contains("canvas")
    }

    private func canvasSessionValue(fromCookieHeader header: String) -> String? {
        for part in header.split(separator: ";") {
            let trimmed = part.trimmingCharacters(in: .whitespaces)
            if trimmed.lowercased().hasPrefix("canvas_session=") {
                let value = String(trimmed.dropFirst("canvas_session=".count))
                return value.isEmpty ? nil : value
            }
        }
        return nil
    }

    private func isBenignNavigationError(_ error: Error) -> Bool {
        let ns = error as NSError
        return ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        let host = (webView.url?.host ?? "").lowercased()
        let canvasHost = (baseURL.host ?? "").lowercased()
        if !canvasHost.isEmpty && (host == canvasHost || host.hasSuffix("." + canvasHost)) {
            statusLabel.text = "Back on Canvas — confirming login…"
            attemptCapture(userInitiated: false)
        } else {
            statusLabel.text = "Complete NetID / Duo… then you should return to Canvas."
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        guard !isBenignNavigationError(error) else { return }
        // Don't overwrite a clearer verify status with a scary message.
        if !verifying {
            statusLabel.text = "Navigation glitch (often harmless after Duo). Use Canvas home or I'm signed in if needed."
        }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard !isBenignNavigationError(error) else { return }
        if !verifying {
            statusLabel.text = "Navigation glitch (often harmless after Duo). Use Canvas home or I'm signed in if needed."
        }
    }
}
