import QtQuick

// Mirrors the design tokens in app/ui/styles.py so the QML login screen
// and the QWidget/QSS screens elsewhere in the app read as one system,
// not two visually different products. `dark` is bound by the caller to
// LoginBridge.darkMode (app/ui/theme.py's persisted light/dark setting) -
// every color below is derived from it, never a second copy to keep in
// sync by hand.
QtObject {
    property bool dark: false

    readonly property color colorBg: dark ? "#000000" : "#f9f9f9"
    readonly property color colorSurface: dark ? "#242424" : "#ffffff"
    readonly property color colorBorder: dark ? "#6c6c6c" : "#e5e5e5"
    readonly property color colorText: dark ? "#fafafa" : "#1a1c1c"
    readonly property color colorTextMuted: dark ? "#b3b3b3" : "#5f5e5e"
    readonly property color colorTextFaint: dark ? "#6c6c6c" : "#a3a3a3"

    readonly property color colorPrimary: dark ? "#fafafa" : "#000000"
    readonly property color colorPrimaryText: dark ? "#000000" : "#ffffff"
    readonly property color colorPrimaryHover: dark ? "#b3b3b3" : "#262626"

    readonly property color colorDanger: dark ? "#f87171" : "#e7000b"
    readonly property color colorDangerBg: dark ? "#3a1414" : "#ffebee"

    readonly property int radiusMd: 4
    readonly property int radiusLg: 8
    readonly property int radiusXl: 24
    readonly property int radiusFull: 9999

    readonly property string fontSans: "Segoe UI"
    readonly property string fontMono: "Consolas"
}
