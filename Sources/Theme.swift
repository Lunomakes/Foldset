import SwiftUI
import AppKit

/// Design tokens: dark graphite surfaces, ink, borders, radii and type, with three inks raised to meet WCAG AA.
enum Theme {
    private static func hex(_ value: UInt32, _ alpha: Double = 1) -> Color {
        Color(.sRGB, red: Double(value >> 16 & 0xFF) / 255, green: Double(value >> 8 & 0xFF) / 255, blue: Double(value & 0xFF) / 255, opacity: alpha)
    }
    // Surfaces
    static let canvas = hex(0x1B1A1F)
    static let surface = hex(0x232227)
    static let control = hex(0x2D2C33)
    static let inverse = hex(0xF2F2F3)
    static let border = Color.white.opacity(0.09)
    static let connector = hex(0x48484A)
    // Ink
    static let ink = hex(0xF2F2F3)
    static let ink2 = hex(0x98989D)
    static let ink3 = hex(0x8E8E93)          // SVG #636366 is 2.6:1 on surface
    static let inverseInk = hex(0x111112)
    // Status. Always paired with a word, never colour alone.
    static let ok = hex(0x30D158)
    static let warn = hex(0xFFD60A)
    static let info = hex(0x409CFF)          // systemBlue is 4.33:1 on surface
    static let bad = hex(0xFF6961)           // systemRed is 4.06:1 on control
    // Shape
    static let radiusCard: CGFloat = 14
    /// Shared by the sidebar footer and the create bar so their top rules form one line.
    static let footerHeight: CGFloat = 64
    // Type. The SVG's 590 / 650 weights map onto SF Pro's continuous axis (semibold = 0.3, bold = 0.4).
    static let title = Font(NSFont.systemFont(ofSize: 15, weight: NSFont.Weight(0.28)))
    static let hero = Font(NSFont.systemFont(ofSize: 19, weight: NSFont.Weight(0.35)))
    static let body = Font.system(size: 12.5)
    static let label = Font.system(size: 11.5, weight: .semibold)
    static let mono = Font.system(size: 12.5, design: .monospaced)
}

enum BrandAsset {
    static let icon: NSImage = Bundle.main.url(forResource: "BrandIcon", withExtension: "png").flatMap { NSImage(contentsOf: $0) } ?? NSApp.applicationIconImage
}

extension View {
    /// Section label: "CREATION" style, with the SVG's 1.4 letter-spacing.
    func sectionLabel() -> some View {
        font(Theme.label).tracking(1.4).foregroundStyle(Theme.ink3).textCase(.uppercase)
    }
    /// Card from the reference: flat surface, hairline border, radius 14.
    func card(radius: CGFloat = Theme.radiusCard, fill: Color = Theme.surface) -> some View {
        background(fill, in: RoundedRectangle(cornerRadius: radius))
            .overlay(RoundedRectangle(cornerRadius: radius).strokeBorder(Theme.border))
    }
}

/// The reference's only filled button: an inverse pill. Secondary actions use native bordered buttons.
struct InverseButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var systemStill
    @AppStorage("reduceMotion") private var preferStill = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(enabled ? Theme.inverseInk : Theme.ink3)
            .padding(.horizontal, 16).frame(height: 30)
            .background(enabled ? Theme.inverse.opacity(configuration.isPressed ? 0.82 : 1) : Theme.control, in: Capsule())
            .overlay(Capsule().strokeBorder(enabled ? .clear : Theme.border))
            .scaleEffect(configuration.isPressed && !(systemStill || preferStill) ? 0.98 : 1)
            .contentShape(Capsule())
    }
}

/// Status dot. Filled = acts, hollow = no change, dashed ring = stopped.
struct StatusDot: View {
    enum Kind { case filled, hollow, stopped }
    let kind: Kind
    let color: Color
    var body: some View {
        ZStack {
            switch kind {
            case .filled: Circle().fill(color)
            case .hollow: Circle().strokeBorder(color, lineWidth: 1.4)
            case .stopped: Circle().strokeBorder(color, style: StrokeStyle(lineWidth: 1.4, dash: [2, 2]))
            }
        }.frame(width: 9, height: 9).accessibilityHidden(true)
    }
}
