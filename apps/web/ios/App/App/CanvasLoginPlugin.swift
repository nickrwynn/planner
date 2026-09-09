import Foundation
import UIKit
import WebKit
import Capacitor

/// Opens an in-app Canvas login WebView, waits for NetID/Duo, then reads the
/// HttpOnly `canvas_session` cookie and returns it to JS.
///
/// Canvas often sets an anonymous `canvas_session` before auth. We only succeed
/// after `/api/v1/users/self` works **inside the WebView** (same cookie jar).
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
    private var statusLabel: UILabel!

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
        navigationItem.rightBarButtonItem = UIBarButtonItem(
            title: "I'm signed in",
            style: .done,
            target: self,
            action: #selector(manualContinueTapped)
        )

        statusLabel = UILabel()
        statusLabel.text = "Log in with NetID / Duo below. When Canvas opens, we connect automatically — or tap I'm signed in."
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

        pollTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in
            self?.attemptCapture(reason: "poll")
        }
    }

    deinit {
        pollTimer?.invalidate()
    }

    @objc private func cancelTapped() {
        finish(.cancelled)
    }

    @objc private func manualContinueTapped() {
        statusLabel.text = "Checking your Canvas login…"
        attemptCapture(reason: "manual")
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

    private func attemptCapture(reason: String) {
        guard !finished, !verifying else { return }
        verifying = true

        // Verify inside the WebView so we use the exact SSO cookie jar (including
        // cookies URLSession would not see the same way).
        let js = """
        (async function() {
          try {
            const res = await fetch('/api/v1/users/self', {
              credentials: 'include',
              headers: { 'Accept': 'application/json' }
            });
            if (!res.ok) return JSON.stringify({ ok: false, status: res.status });
            const user = await res.json();
            if (!user || !user.id) return JSON.stringify({ ok: false, status: res.status });
            return JSON.stringify({ ok: true, id: String(user.id), name: user.name || '' });
          } catch (e) {
            return JSON.stringify({ ok: false, error: String(e) });
          }
        })();
        """

        // fetch relative URL only works on the Canvas origin; if still on CAS/Duo, skip.
        let host = (webView.url?.host ?? "").lowercased()
        let canvasHost = (baseURL.host ?? "").lowercased()
        let onCanvasHost = !canvasHost.isEmpty && (host == canvasHost || host.hasSuffix("." + canvasHost) || canvasHost.hasSuffix("." + host))

        guard onCanvasHost else {
            verifying = false
            if reason == "manual" {
                statusLabel.text = "Finish Duo, wait until you see Canvas, then tap I'm signed in."
            }
            return
        }

        webView.evaluateJavaScript(js) { [weak self] result, error in
            guard let self, !self.finished else { return }

            func fail(_ message: String) {
                self.verifying = false
                if reason == "manual" {
                    self.statusLabel.text = message
                }
            }

            if let error {
                fail("Still on Canvas, but login check failed. Tap I'm signed in again. (\(error.localizedDescription))")
                return
            }

            let raw = (result as? String) ?? ""
            guard
                let data = raw.data(using: .utf8),
                let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                (json["ok"] as? Bool) == true
            else {
                let status = (try? JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any])?["status"]
                fail("Canvas is open, but you're not fully signed in yet (status \(status ?? "n/a")). Finish login, then tap I'm signed in.")
                return
            }

            self.dataStore.httpCookieStore.getAllCookies { cookies in
                let session = cookies.first(where: { self.isCanvasSessionCookie($0) })?.value
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                DispatchQueue.main.async {
                    self.verifying = false
                    guard !self.finished else { return }
                    guard let session, !session.isEmpty else {
                        self.statusLabel.text = "Signed into Canvas in the browser, but no canvas_session cookie was found. Try Cancel and sign in again."
                        return
                    }
                    self.statusLabel.text = "Signed in — connecting StudyFlows…"
                    self.finish(.success(session))
                }
            }
        }
    }

    private func isCanvasSessionCookie(_ cookie: HTTPCookie) -> Bool {
        guard cookie.name == "canvas_session" else { return false }
        let host = (baseURL.host ?? "").lowercased()
        let domain = cookie.domain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        if host.isEmpty { return true }
        return host == domain
            || host.hasSuffix("." + domain)
            || domain.hasSuffix(host)
            || domain.contains("canvas")
            || domain.contains("instructure")
    }

    private func isBenignNavigationError(_ error: Error) -> Bool {
        let ns = error as NSError
        // -999 = request cancelled (normal during SSO redirects)
        return ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        let host = webView.url?.host ?? ""
        if host.localizedCaseInsensitiveContains(baseURL.host ?? "canvas") {
            statusLabel.text = "Canvas loaded — confirming login…"
            attemptCapture(reason: "didFinish")
        } else {
            statusLabel.text = "Complete NetID / Duo… you'll return to Canvas next."
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        guard !isBenignNavigationError(error) else { return }
        statusLabel.text = "Page hiccup after Duo is normal — wait for Canvas, or tap I'm signed in."
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard !isBenignNavigationError(error) else { return }
        statusLabel.text = "Page hiccup after Duo is normal — wait for Canvas, or tap I'm signed in."
    }
}
