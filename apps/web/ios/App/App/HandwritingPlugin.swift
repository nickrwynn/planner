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
        CAPPluginMethod(name: "recognize", returnType: CAPPluginReturnPromise)
    ]

    @objc func isAvailable(_ call: CAPPluginCall) {
        call.resolve(["available": true])
    }

    @objc func recognize(_ call: CAPPluginCall) {
        guard let base64 = call.getString("imageBase64")?.trimmingCharacters(in: .whitespacesAndNewlines),
              !base64.isEmpty
        else {
            call.reject("imageBase64 is required")
            return
        }

        // Accept both raw base64 and data URLs.
        let payload: String
        if let comma = base64.range(of: ","), base64.hasPrefix("data:") {
            payload = String(base64[comma.upperBound...])
        } else {
            payload = base64
        }

        guard let data = Data(base64Encoded: payload, options: .ignoreUnknownCharacters),
              let image = UIImage(data: data),
              let cgImage = image.cgImage
        else {
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
