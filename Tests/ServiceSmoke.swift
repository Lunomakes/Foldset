import AppKit
import Foundation
let target = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: target, withIntermediateDirectories: false)
let app = NSApplication.shared
let pb = NSPasteboard.withUniqueName()
pb.writeObjects([target as NSURL])
print("Pasteboard types: \(pb.types ?? [])")
print("Objects: \(pb.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) ?? [])")
let success = NSPerformService("Foldset：使用默认模板创建", pb)
// Keep the sender and pasteboard alive while a cold service launch is delivered.
RunLoop.current.run(until: Date().addingTimeInterval(2))
pb.releaseGlobally()
print("Default service returned: \(success)")
let names = try FileManager.default.contentsOfDirectory(atPath: target.path).sorted()
print(names.joined(separator: "\n"))
let expectedCount = CommandLine.arguments.count > 2 ? Int(CommandLine.arguments[2])! : 5
if !success || names.count != expectedCount { exit(1) }
