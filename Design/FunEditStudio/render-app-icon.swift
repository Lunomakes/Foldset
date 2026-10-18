import AppKit
// Builds the Dock icon: the transparent For Editor artwork on a deep violet squircle.
// macOS 26+ puts any icon that is not an Icon Composer asset on a pale plate in the Dock, even an icns that
// already fills the squircle, so the icon ships as a compiled Assets.car (CFBundleIconName) plus an icns fallback.
// Usage (needs Xcode for actool): swift render-app-icon.swift <Design/FunEditStudio>
// Writes Foldset.icon/Assets/{background,artwork}.png and compiles Foldset-AppIcon/{Assets.car,Foldset.icns}.
// actool needs absolute paths.
let root=URL(fileURLWithPath:CommandLine.arguments[1]).standardizedFileURL.path
let art=NSImage(contentsOfFile:root+"/Foldset-For-Editor.png")!.cgImage(forProposedRect:nil,context:nil,hints:nil)!
func color(_ h:UInt32)->CGColor {CGColor(red:CGFloat(h>>16&255)/255,green:CGFloat(h>>8&255)/255,blue:CGFloat(h&255)/255,alpha:1)}
func layer(_ name:String,_ draw:(CGContext)->Void) throws {
    let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1024,pixelsHigh:1024,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    let c=NSGraphicsContext(bitmapImageRep:rep)!.cgContext
    c.interpolationQuality = .high
    draw(c)
    try rep.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:root+"/Foldset.icon/Assets/"+name))
}
// Icon Composer layers span the whole squircle, which the system masks and pads.
try layer("background.png"){c in
    let g=CGGradient(colorsSpace:CGColorSpaceCreateDeviceRGB(),colors:[color(0x3A3350),color(0x1E1A2B)] as CFArray,locations:[0,1])!
    c.drawLinearGradient(g,start:CGPoint(x:512,y:1024),end:CGPoint(x:512,y:0),options:[])
}
try layer("artwork.png"){c in
    // The artwork's visible folder spans about 600 of its 1024 px; 1.39x fills about 82% of the squircle.
    let k:CGFloat=1024*1.392
    c.draw(art,in:CGRect(x:(1024-k)/2,y:(1024-k)/2-10,width:k,height:k))
}
let out=root+"/Foldset-AppIcon"
try FileManager.default.createDirectory(atPath:out,withIntermediateDirectories:true)
let actool=Process()
actool.executableURL=URL(fileURLWithPath:"/usr/bin/xcrun")
actool.arguments=["actool",root+"/Foldset.icon","--compile",out,"--platform","macosx","--minimum-deployment-target","14.0",
                  "--app-icon","Foldset","--output-partial-info-plist",NSTemporaryDirectory()+"Foldset-icon-partial.plist"]
try actool.run(); actool.waitUntilExit()
guard actool.terminationStatus==0 else { fatalError("actool failed") }
