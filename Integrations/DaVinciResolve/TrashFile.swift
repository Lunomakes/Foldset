import Foundation

// One explicitly selected file per invocation; never permanently remove items.
do {
    guard CommandLine.arguments.count == 2 else { throw NSError(domain: "Foldset", code: 1, userInfo: [NSLocalizedDescriptionKey: "需要一个文件路径"]) }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
    guard values.isRegularFile == true && values.isSymbolicLink != true else { throw NSError(domain: "Foldset", code: 2, userInfo: [NSLocalizedDescriptionKey: "只允许普通文件"]) }
    var resulting: NSURL?
    try FileManager.default.trashItem(at: url, resultingItemURL: &resulting)
    let data = try JSONSerialization.data(withJSONObject: ["trashed": true, "path": resulting?.path ?? ""])
    print(String(decoding: data, as: UTF8.self))
} catch {
    FileHandle.standardError.write(Data(error.localizedDescription.utf8))
    exit(1)
}
