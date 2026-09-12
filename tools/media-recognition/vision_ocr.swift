import Foundation
import ImageIO
import Vision

func emit(_ value: [String: Any]) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

guard CommandLine.arguments.count == 3 else {
    emit(["ok": false, "error_code": "invalid_provider_response"])
}

let path = CommandLine.arguments[1]
let attemptID = CommandLine.arguments[2]
guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    emit(["ok": false, "error_code": "invalid_media", "attempt_id": attemptID])
}

let request = VNRecognizeTextRequest { request, error in
    if error != nil {
        emit(["ok": false, "error_code": "provider_unavailable", "attempt_id": attemptID])
    }
    let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
    let lines = observations.compactMap { observation in
        observation.topCandidates(1).first?.string
    }.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    let text = lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty {
        emit(["ok": false, "error_code": "no_text_detected", "attempt_id": attemptID])
    }
    emit(["ok": true, "text": text, "attempt_id": attemptID])
}
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["zh-Hans", "en-US"]

do {
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
} catch {
    emit(["ok": false, "error_code": "provider_unavailable", "attempt_id": attemptID])
}
