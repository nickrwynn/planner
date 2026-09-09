import Foundation
import UIKit
import WebKit
import Capacitor

/// Opens an in-app Canvas login WebView, waits for NetID/Duo, then reads the
/// HttpOnly `canvas_session` cookie and returns it to JS.
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

        statusLabel = UILabel()
        statusLabel.text = "Log in with NetID / Duo. We’ll connect automatically when Canvas is ready."
        statusLabel.font = .preferredFont(forTextStyle: .footnote)
        statusLabel.textColor = .secondaryLabel
        statusLabel.numberOfLines = 0
        statusLabel.translatesAutoresizingMaskIntoConstraints = false

        let config = WKWebViewConfiguration()
        config.websiteDataStore = dataStore
        config.defaultWebpagePreferences.allowsContentJavaScript = true

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

        let loginURL = baseURL.appendingPathComponent("login")
        webView.load(URLRequest(url: loginURL))

        pollTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.checkForSessionCookie()
        }
    }

    deinit {
        pollTimer?.invalidate()
    }

    @objc private func cancelTapped() {
        finish(.cancelled)
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

    private func checkForSessionCookie() {
        dataStore.httpCookieStore.getAllCookies { [weak self] cookies in
            guard let self, !self.finished else { return }
            guard let cookie = cookies.first(where: { self.isCanvasSessionCookie($0) }) else { return }
            let value = cookie.value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { return }
            DispatchQueue.main.async {
                self.statusLabel.text = "Signed in — connecting StudyFlows…"
                self.finish(.success(value))
            }
        }
    }

    private func isCanvasSessionCookie(_ cookie: HTTPCookie) -> Bool {
        guard cookie.name == "canvas_session" else { return false }
        let host = (baseURL.host ?? "").lowercased()
        let domain = cookie.domain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        if host.isEmpty { return true }
        return host == domain || host.hasSuffix("." + domain) || domain.hasSuffix(host) || domain.contains("canvas")
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        checkForSessionCookie()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        // Keep the sheet open for Duo / network blips; only fail hard on cancel.
        statusLabel.text = "Still loading… If Duo prompts, complete it here."
    }
}
