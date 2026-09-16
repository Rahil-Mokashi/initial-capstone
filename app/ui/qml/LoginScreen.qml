import QtQuick
import QtQuick.Controls.Basic

// The animated replacement for the old QWidget login form
// (app/ui/login_window.py, pre-2026-09-02). All authentication logic
// stays in Python (LoginBridge -> AuthService) - this file is
// presentation and motion only: entrance fade, focus/hover transitions,
// and an animated error banner. `bridge` is injected as a QML context
// property by LoginWindow.__init__ before this file is loaded.
Rectangle {
    id: root
    color: theme.colorBg

    Theme {
        id: theme
        dark: bridge.darkMode
    }

    // 2026-09-16, user-reported crash: a genuine native
    // STATUS_STACK_OVERFLOW (confirmed in the Windows Application event
    // log, faulting inside pyside6.abi3.dll), reproduced reliably -
    // with real interactive keyboard/mouse input, not just a test
    // harness, run repeatedly - by pressing Return in EITHER text
    // field or clicking Sign In. Isolated by exhaustive testing to one
    // exact fact: calling ANY Python-registered Slot synchronously
    // from inside this QML while its own input-event delivery (a
    // TextField's Return keypress, a Button's click) is still live on
    // the native call stack crashes, regardless of which field, which
    // Slot, or what that Slot's own body does - even a truly empty one
    // crashes. Four different attempts to defer the call past that
    // live event all failed identically (Python-side
    // QTimer.singleShot, twice, at two different points in the call
    // chain; QML-side Qt.callLater, twice, deferring first just the
    // error-handling side effect below, then the login call itself) -
    // which is what ruled out re-entrancy/timing as the mechanism and
    // pointed at the call boundary itself: entering Python at all from
    // this exact native context is unsafe, no matter when.
    //
    // The fix is therefore structural, not another deferral: this file
    // never calls into Python from onAccepted/onClicked at all.
    // usernameField/passwordField push their text to bridge.username/
    // bridge.password continuously as the user types (onTextChanged -
    // a different, unrelated native code path from Return/click
    // handling, and not implicated by any of the crashes above).
    // Submitting only ever touches submitTrigger, a plain QML
    // property with no Python involvement - LoginWindow.py is what
    // actually calls bridge.submit(), connected to this property's
    // own auto-generated submitTriggerChanged signal with an explicit
    // Qt.QueuedConnection, which Qt guarantees only dispatches once
    // the event loop is back at its own outermost frame - genuinely
    // after the input event has finished, not just deferred within
    // the same QML update cycle the way Qt.callLater is.
    property int submitTrigger: 0
    function requestSubmit() { submitTrigger++ }

    Column {
        id: centerColumn
        anchors.centerIn: parent
        width: 380
        spacing: 36
        opacity: 0

        Component.onCompleted: entranceAnimation.start()
        NumberAnimation {
            id: entranceAnimation
            target: centerColumn
            property: "opacity"
            from: 0
            to: 1
            duration: 420
            easing.type: Easing.OutCubic
        }

        // --- Brand header ---
        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 10

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 16

                Rectangle {
                    width: 56
                    height: 56
                    radius: 28
                    color: theme.colorPrimary
                    border.color: theme.colorSurface
                    border.width: 1.5

                    Text {
                        anchors.centerIn: parent
                        text: "F"
                        color: theme.colorPrimaryText
                        font.pixelSize: 26
                        font.bold: true
                        font.family: theme.fontSans
                    }
                }

                Text {
                    text: "FuelDesk"
                    color: theme.colorText
                    font.pixelSize: 32
                    font.bold: true
                    font.family: theme.fontSans
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Secure sign-in to your operations platform"
                color: theme.colorTextMuted
                font.pixelSize: 14
                font.family: theme.fontSans
            }
        }

        // --- Credentials card ---
        Rectangle {
            id: card
            width: 380
            radius: theme.radiusXl
            color: theme.colorSurface
            border.color: theme.colorBorder
            border.width: 1
            height: cardColumn.implicitHeight + 64

            Behavior on height {
                NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
            }

            Column {
                id: cardColumn
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 32
                spacing: 14

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    radius: theme.radiusFull
                    color: theme.colorSurface
                    border.color: theme.colorBorder
                    border.width: 1.5
                    width: pillText.implicitWidth + 20
                    height: pillText.implicitHeight + 10

                    Text {
                        id: pillText
                        anchors.centerIn: parent
                        text: "SECURE SIGN-IN"
                        font.pixelSize: 12
                        font.bold: true
                        font.family: theme.fontMono
                        color: theme.colorText
                    }
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Welcome back"
                    font.pixelSize: 24
                    font.bold: true
                    font.family: theme.fontSans
                    color: theme.colorText
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Sign in to access your dashboard"
                    font.pixelSize: 14
                    font.family: theme.fontSans
                    color: theme.colorTextMuted
                }

                Item { width: 1; height: 8 }

                Text {
                    text: "USERNAME"
                    font.pixelSize: 11
                    font.bold: true
                    font.family: theme.fontSans
                    color: theme.colorTextMuted
                }

                TextField {
                    id: usernameField
                    objectName: "usernameField"
                    width: parent.width
                    placeholderText: "Enter your username"
                    font.pixelSize: 14
                    font.family: theme.fontSans
                    color: theme.colorText
                    selectByMouse: true
                    KeyNavigation.tab: passwordField
                    onAccepted: passwordField.forceActiveFocus()
                    onTextChanged: bridge.username = text

                    background: Rectangle {
                        radius: theme.radiusMd
                        color: theme.colorSurface
                        border.color: usernameField.activeFocus ? theme.colorText : theme.colorBorder
                        border.width: usernameField.activeFocus ? 2 : 1.5
                    }
                }

                Text {
                    text: "PASSWORD"
                    font.pixelSize: 11
                    font.bold: true
                    font.family: theme.fontSans
                    color: theme.colorTextMuted
                }

                Row {
                    width: parent.width
                    spacing: 8

                    TextField {
                        id: passwordField
                        objectName: "passwordField"
                        width: parent.width - toggleButton.width - 8
                        placeholderText: "Your password"
                        font.pixelSize: 14
                        font.family: theme.fontSans
                        color: theme.colorText
                        selectByMouse: true
                        echoMode: toggleButton.checked ? TextInput.Normal : TextInput.Password
                        onAccepted: root.requestSubmit()
                        onTextChanged: bridge.password = text

                        background: Rectangle {
                            radius: theme.radiusMd
                            color: theme.colorSurface
                            border.color: passwordField.activeFocus ? theme.colorText : theme.colorBorder
                            border.width: passwordField.activeFocus ? 2 : 1.5
                        }
                    }

                    Button {
                        id: toggleButton
                        objectName: "togglePasswordButton"
                        checkable: true
                        text: checked ? "Hide" : "Show"
                        font.pixelSize: 12
                        font.bold: true
                        font.family: theme.fontSans
                        height: passwordField.implicitHeight

                        background: Rectangle {
                            radius: theme.radiusMd
                            color: theme.colorSurface
                            border.color: theme.colorBorder
                            border.width: 1.5
                        }
                        contentItem: Text {
                            text: toggleButton.text
                            color: theme.colorTextMuted
                            font: toggleButton.font
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }

                Item { width: 1; height: 10 }

                Button {
                    id: signInButton
                    objectName: "signInButton"
                    width: parent.width
                    height: 44
                    enabled: !bridge.busy
                    text: bridge.busy ? "Signing in…" : "Sign In →"
                    onClicked: root.requestSubmit()

                    background: Rectangle {
                        radius: theme.radiusFull
                        color: !signInButton.enabled
                            ? theme.colorBorder
                            : (signInButton.pressed || signInButton.hovered ? theme.colorPrimaryHover : theme.colorPrimary)
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }
                    contentItem: Text {
                        text: signInButton.text
                        color: theme.colorPrimaryText
                        font.pixelSize: 14
                        font.bold: true
                        font.family: theme.fontSans
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Rectangle {
                    id: errorBanner
                    objectName: "errorBanner"
                    width: parent.width
                    visible: opacity > 0
                    opacity: bridge.error.length > 0 ? 1 : 0
                    height: bridge.error.length > 0 ? errorText.implicitHeight + 16 : 0
                    radius: theme.radiusLg
                    color: theme.colorDangerBg
                    border.color: theme.colorDanger
                    border.width: 1
                    clip: true

                    Behavior on opacity { NumberAnimation { duration: 150 } }
                    Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }

                    Text {
                        id: errorText
                        anchors.centerIn: parent
                        width: parent.width - 16
                        text: bridge.error
                        color: theme.colorDanger
                        font.pixelSize: 12
                        font.family: theme.fontSans
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                Item { width: 1; height: 6 }

                Text {
                    width: parent.width
                    text: "Locked out or need a password reset? Contact your system administrator."
                    color: theme.colorTextFaint
                    font.pixelSize: 12
                    font.family: theme.fontSans
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }

    Connections {
        target: bridge
        function onErrorChanged() {
            // Safe to run directly, no deferral needed: errorChanged
            // only ever fires from inside bridge.submit(), which
            // LoginWindow.py only ever invokes via a Qt.QueuedConnection
            // (see this file's own long comment on submitTrigger above)
            // - by the time this handler runs, the original Return/click
            // event has already finished being delivered.
            if (bridge.error.length > 0) {
                passwordField.text = ""
                passwordField.forceActiveFocus()
            }
        }
    }

    Component.onCompleted: usernameField.forceActiveFocus()
}
