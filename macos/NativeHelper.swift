// Fixed-purpose local OCR and app-owned Keychain slots. No network or input files.
import Foundation
import Vision
import Security

let service = "local.traderoom.desktop.espn"
// Fresh app-owned slots allow metadata commit before retiring prior credentials.
let account = CommandLine.arguments.count > 2 ? CommandLine.arguments[2] : "league"
guard account.range(of: "^league(-[0-9a-f]{32})?$", options: .regularExpression) != nil else { exit(1) }
let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                           kSecAttrService as String: service, kSecAttrAccount as String: account,
                           kSecAttrSynchronizable as String: false]
func fail() -> Never { exit(1) } // Never print OS errors, cookies or recognized text to stderr.
let action = CommandLine.arguments.dropFirst().first ?? ""
switch action {
case "ocr-check":
    do {
        let languages = try VNRecognizeTextRequest().supportedRecognitionLanguages()
        guard languages.contains("en-US") else { fail() }
        print("apple-vision-en-US")
    } catch { fail() }
case "ocr":
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard !data.isEmpty, data.count <= 6 * 1024 * 1024 else { fail() }
    let request = VNRecognizeTextRequest()
    // Revision 2 is the local English model available since macOS 11.
    request.revision = VNRecognizeTextRequestRevision2
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    request.automaticallyDetectsLanguage = false
    do {
        try VNImageRequestHandler(data: data, options: [:]).perform([request])
        let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
        FileHandle.standardOutput.write(Data(text.prefix(12000).utf8))
    } catch { fail() }
case "secret-save":
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard data.count <= 20000, (try? JSONSerialization.jsonObject(with: data)) is [String: String] else { fail() }
    let attrs: [String: Any] = [kSecValueData as String: data,
        kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        kSecAttrLabel as String: "Trade Room — local ESPN settings"]
    let status = SecItemUpdate(query as CFDictionary, attrs as CFDictionary)
    if status == errSecItemNotFound {
        guard SecItemAdd(query.merging(attrs) { _, new in new } as CFDictionary, nil) == errSecSuccess else { fail() }
    } else if status != errSecSuccess { fail() }
case "secret-read":
    var request = query
    request[kSecReturnData as String] = true
    request[kSecMatchLimit as String] = kSecMatchLimitOne
    var item: CFTypeRef?
    guard SecItemCopyMatching(request as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { fail() }
    FileHandle.standardOutput.write(data)
case "secret-delete":
    let status = SecItemDelete(query as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else { fail() }
default: fail()
}
