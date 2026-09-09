import Foundation
import UIKit
import Vision
import Capacitor

/// On-device handwriting/text recognition using Apple's Vision framework.
///
/// Runs entirely on the device (no network, no API key) so recognition is instant
/// while writing with Apple Pencil. Vision cannot produce LaTeX, so math mode
/// returns plain text and the caller decides whether to refine it elsewhere.
@objc(HandwritingPlugin)
public class HandwritingPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "HandwritingPlugin"
    public let jsName = "Handwriting"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isAvailable", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "recognize", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "recognizeSymbols", returnType: CAPPluginReturnPromise)
    ]

    /// Per-character boxes for the math recognizer's layout pass.
    ///
    /// One Vision request for the whole image, then each character's box is
    /// read back from the candidate. Language correction is off so Vision does
    /// not "helpfully" turn symbols into words.
    @objc func recognizeSymbols(_ call: CAPPluginCall) {
        guard let cgImage = Self.decodeImage(call.getString("imageBase64")) else {
            call.reject("Could not decode image")
            return
        }

        let width = Double(cgImage.width)
        let height = Double(cgImage.height)

        let request = VNRecognizeTextRequest { request, error in
            if let error {
                call.reject("Recognition failed: \(error.localizedDescription)")
                return
            }
            var symbols: [[String: Any]] = []
            for observation in (request.results as? [VNRecognizedTextObservation]) ?? [] {
                guard let candidate = observation.topCandidates(1).first else { continue }
                let text = candidate.string
                var index = text.startIndex
                while index < text.endIndex {
                    let next = text.index(after: index)
                    let character = String(text[index..<next])
                    if character.trimmingCharacters(in: .whitespaces).isEmpty {
                        index = next
                        continue
                    }
                    if let box = try? candidate.boundingBox(for: index..<next) {
                        // Vision is normalized with the origin at bottom-left.
                        let rect = box.boundingBox
                        symbols.append([
                            "char": character,
                            "x": rect.minX * width,
                            "y": (1.0 - rect.maxY) * height,
                            "w": rect.width * width,
                            "h": rect.height * height
                        ])
                    }
                    index = next
                }
            }
            call.resolve([
                "symbols": symbols,
                "width": width,
                "height": height
            ])
        }

        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US"]
        request.usesLanguageCorrection = false
        if #available(iOS 16.0, *) {
            request.revision = VNRecognizeTextRequestRevision3
        }

        DispatchQueue.global(qos: .userInitiated).async {
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            do {
                try handler.perform([request])
            } catch {
                call.reject("Recognition failed: \(error.localizedDescription)")
            }
        }
    }

    /// Accepts both raw base64 and data URLs.
    private static func decodeImage(_ raw: String?) -> CGImage? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return nil
        }
        let payload: String
        if raw.hasPrefix("data:"), let comma = raw.range(of: ",") {
            payload = String(raw[comma.upperBound...])
        } else {
            payload = raw
        }
        guard let data = Data(base64Encoded: payload, options: .ignoreUnknownCharacters),
              let image = UIImage(data: data)
        else {
            return nil
        }
        return image.cgImage
    }

    @objc func isAvailable(_ call: CAPPluginCall) {
        call.resolve(["available": true])
    }

    @objc func recognize(_ call: CAPPluginCall) {
        guard let cgImage = Self.decodeImage(call.getString("imageBase64")) else {
            call.reject("Could not decode image")
            return
        }

        let request = VNRecognizeTextRequest { request, error in
            if let error {
                call.reject("Recognition failed: \(error.localizedDescription)")
                return
            }
            let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
            var lines: [String] = []
            for observation in observations {
                if let candidate = observation.topCandidates(1).first {
                    let text = candidate.string.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !text.isEmpty { lines.append(text) }
                }
            }
            call.resolve([
                "text": lines.joined(separator: "\n"),
                "lineCount": lines.count
            ])
        }

        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["en-US"]
        // Language correction helps joined handwriting; disable for math-ish input
        // so symbols are not "corrected" into words.
        let mode = call.getString("mode") ?? "text"
        request.usesLanguageCorrection = mode != "math"
        if #available(iOS 16.0, *) {
            request.revision = VNRecognizeTextRequestRevision3
        }

        // Off the main thread so ink stays responsive.
        DispatchQueue.global(qos: .userInitiated).async {
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            do {
                try handler.perform([request])
            } catch {
                call.reject("Recognition failed: \(error.localizedDescription)")
            }
        }
    }
}
