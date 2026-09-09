import Foundation
import UIKit
import Capacitor

/// On-device writing assistance: word completion and spell suggestions.
///
/// Uses `UITextChecker`, Apple's built-in on-device dictionary. No network,
/// no API key, and fast enough to call on every keystroke.
@objc(TextAssistPlugin)
public class TextAssistPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "TextAssistPlugin"
    public let jsName = "TextAssist"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isAvailable", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "completeWord", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "spellSuggestions", returnType: CAPPluginReturnPromise)
    ]

    private let checker = UITextChecker()

    @objc func isAvailable(_ call: CAPPluginCall) {
        call.resolve(["available": true])
    }

    /// Complete the partial word at the end of `prefix`.
    @objc func completeWord(_ call: CAPPluginCall) {
        let prefix = call.getString("prefix") ?? ""
        let language = call.getString("language") ?? "en_US"
        let partial = Self.trailingWord(of: prefix)

        guard partial.count >= 2 else {
            call.resolve(["completions": [String]()])
            return
        }

        let range = NSRange(location: 0, length: (partial as NSString).length)
        let found = checker.completions(forPartialWordRange: range, in: partial, language: language) ?? []
        let limit = call.getInt("limit") ?? 5
        call.resolve([
            "partial": partial,
            "completions": Array(found.prefix(max(1, limit)))
        ])
    }

    /// Misspellings and corrections for a block of text.
    @objc func spellSuggestions(_ call: CAPPluginCall) {
        guard let text = call.getString("text"), !text.isEmpty else {
            call.resolve(["issues": [[String: Any]]()])
            return
        }
        let language = call.getString("language") ?? "en_US"
        let ns = text as NSString
        var issues: [[String: Any]] = []
        var offset = 0

        while offset < ns.length && issues.count < 50 {
            let searchRange = NSRange(location: offset, length: ns.length - offset)
            let bad = checker.rangeOfMisspelledWord(
                in: text,
                range: searchRange,
                startingAt: offset,
                wrap: false,
                language: language
            )
            if bad.location == NSNotFound { break }
            let word = ns.substring(with: bad)
            let guesses = checker.guesses(forWordRange: bad, in: text, language: language) ?? []
            issues.append([
                "word": word,
                "start": bad.location,
                "length": bad.length,
                "suggestions": Array(guesses.prefix(4))
            ])
            offset = bad.location + bad.length
        }

        call.resolve(["issues": issues])
    }

    /// Last whitespace-delimited word fragment, letters/apostrophes only.
    private static func trailingWord(of text: String) -> String {
        let allowed = CharacterSet.letters.union(CharacterSet(charactersIn: "'"))
        var chars: [Character] = []
        for scalar in text.unicodeScalars.reversed() {
            if allowed.contains(scalar) {
                chars.append(Character(scalar))
            } else {
                break
            }
        }
        return String(chars.reversed())
    }
}
