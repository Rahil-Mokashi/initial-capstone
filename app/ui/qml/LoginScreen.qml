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

    // Responsive form width (2026-09-25, login UI pass): a fixed 380px
    // card looked fine at the window's default size but either clipped
    // against the edges on a narrow/resized window or looked stranded
    // in empty space on a wide one - neither of which a web page would
    // do. This recomputes on every root.width change (QQuickWidget's
    // resizeMode keeps root matching the window exactly), floored at
    // 320 so fields never get too cramped to use, capped at 460 so the
    // card doesn't stretch into an awkward wide strip on a maximized
    // window.
    property real formWidth: Math.max(320, Math.min(460, width - 64))

    Column {
        id: centerColumn
        anchors.centerIn: parent
        width: root.formWidth
        spacing: 32
        opacity: 0
        scale: 0.96
        transformOrigin: Item.Center

        // Fade+scale entrance, not fade alone (2026-09-25): opacity
        // changing alone reads as the page simply finishing loading;
        // pairing it with a small scale-up (0.96 -> 1.0) reads as the
        // card actually arriving, which is the first thing that should
        // tell a user this is a live, responsive interface rather than
        // a static image.
        Component.onCompleted: entranceAnimation.start()
        ParallelAnimation {
            id: entranceAnimation
            NumberAnimation {
                target: centerColumn
                property: "opacity"
                from: 0
                to: 1
                duration: 420
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: centerColumn
                property: "scale"
                from: 0.96
                to: 1
                duration: 420
                easing.type: Easing.OutCubic
            }
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
        }

        // --- Credentials card ---
        Rectangle {
            id: card
            width: root.formWidth
            radius: theme.radiusXl
            color: theme.colorSurface
            border.color: theme.colorBorder
            border.width: 1
            height: cardColumn.implicitHeight + 64

            Behavior on height {
                NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
            }

            // A `transform` rather than animating `x` directly (2026-
            // 09-25): `card` sits inside centerColumn, a Column
            // Positioner, which owns and continually reasserts each
            // child's x/y itself - animating card.x directly would
            // fight the Positioner's own layout pass every frame.
            // Translate is a separate rendering-level offset the
            // Positioner never touches, so the shake below can move the
            // card without that fight. Triggered from the Connections
            // block below on every failed login.
            transform: Translate { id: shakeTransform }
            SequentialAnimation {
                id: shakeAnimation
                NumberAnimation { target: shakeTransform; property: "x"; to: -10; duration: 55 }
                NumberAnimation { target: shakeTransform; property: "x"; to: 10; duration: 55 }
                NumberAnimation { target: shakeTransform; property: "x"; to: -6; duration: 55 }
                NumberAnimation { target: shakeTransform; property: "x"; to: 6; duration: 55 }
                NumberAnimation { target: shakeTransform; property: "x"; to: 0; duration: 55 }
            }

            Column {
                id: cardColumn
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 32
                spacing: 16

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Welcome back"
                    font.pixelSize: 26
                    font.bold: true
                    font.family: theme.fontSans
                    color: theme.colorText
                }

                Item { width: 1; height: 8 }

                Text {
                    text: "Username"
                    font.pixelSize: 16
                    font.bold: true
                    font.family: theme.fontSans
                    color: theme.colorTextMuted
                }

                TextField {
                    id: usernameField
                    objectName: "usernameField"
                    width: parent.width
                    height: 52
                    placeholderText: "Enter your username"
                    font.pixelSize: 20
                    font.family: theme.fontSans
                    color: theme.colorText
                    leftPadding: 16
                    rightPadding: 16
                    selectByMouse: true
                    hoverEnabled: true
                    KeyNavigation.tab: passwordField
                    onAccepted: passwordField.forceActiveFocus()
                    onTextChanged: bridge.username = text

                    background: Rectangle {
                        radius: theme.radiusMd
                        color: theme.colorSurface
                        border.color: usernameField.activeFocus
                            ? theme.colorText
                            : (usernameField.hovered ? theme.colorTextMuted : theme.colorBorder)
                        border.width: usernameField.activeFocus ? 2 : 1.5
                        // A snap change on focus/hover reads as the field
                        // just being in one of two fixed states; animating
                        // it reads as the field actually responding to you.
                        Behavior on border.color { ColorAnimation { duration: 120 } }
                        Behavior on border.width { NumberAnimation { duration: 120 } }
                    }
                }

                Text {
                    text: "Password"
                    font.pixelSize: 16
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
                        height: 52
                        placeholderText: "Your password"
                        font.pixelSize: 20
                        font.family: theme.fontSans
                        color: theme.colorText
                        leftPadding: 16
                        rightPadding: 16
                        selectByMouse: true
                        hoverEnabled: true
                        echoMode: toggleButton.checked ? TextInput.Normal : TextInput.Password
                        onAccepted: root.requestSubmit()
                        onTextChanged: bridge.password = text

                        // Auto-hide (2026-09-25): the moment this field
                        // isn't the one being typed into, force the
                        // password back behind dots - so "Show" pressed
                        // a minute ago doesn't leave a password sitting
                        // in plain text on screen after the user has
                        // moved on to the Sign In button or walked away.
                        // toggleButton.focusPolicy is set to Qt.NoFocus
                        // below specifically so *clicking Show/Hide
                        // itself* doesn't count as "leaving" the field
                        // and immediately undo the reveal it just asked
                        // for.
                        onActiveFocusChanged: {
                            if (!activeFocus) {
                                toggleButton.checked = false
                            }
                        }

                        background: Rectangle {
                            radius: theme.radiusMd
                            color: theme.colorSurface
                            border.color: passwordField.activeFocus
                                ? theme.colorText
                                : (passwordField.hovered ? theme.colorTextMuted : theme.colorBorder)
                            border.width: passwordField.activeFocus ? 2 : 1.5
                            Behavior on border.color { ColorAnimation { duration: 120 } }
                            Behavior on border.width { NumberAnimation { duration: 120 } }
                        }
                    }

                    Button {
                        id: toggleButton
                        objectName: "togglePasswordButton"
                        checkable: true
                        focusPolicy: Qt.NoFocus
                        hoverEnabled: true
                        text: checked ? "Hide" : "Show"
                        font.pixelSize: 14
                        font.bold: true
                        font.family: theme.fontSans
                        height: passwordField.height
                        scale: pressed ? 0.94 : 1.0
                        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                        // Button.cursorShape isn't a settable QML property
                        // on this Qt version (confirmed by a QML load
                        // error when tried directly) - HoverHandler is a
                        // separate pointer-handling child that does
                        // expose one, without interfering with the
                        // Button's own click/hover handling.
                        HoverHandler { cursorShape: Qt.PointingHandCursor }

                        // Auto-hide on a timer too (2026-09-25): blur
                        // alone doesn't cover the case where someone
                        // presses Show and then just keeps looking at
                        // the screen without moving focus away - a
                        // revealed password left up indefinitely is the
                        // same shoulder-surfing risk the blur handler
                        // exists to close. Any explicit action resets
                        // it: toggling Show again restarts the clock,
                        // and pressing Hide (or the blur handler above)
                        // sets checked false, which stops it here.
                        Timer {
                            id: autoHideTimer
                            interval: 4000
                            onTriggered: toggleButton.checked = false
                        }
                        onCheckedChanged: {
                            if (checked) {
                                autoHideTimer.restart()
                            } else {
                                autoHideTimer.stop()
                            }
                        }

                        background: Rectangle {
                            radius: theme.radiusMd
                            color: toggleButton.hovered ? theme.colorBg : theme.colorSurface
                            border.color: toggleButton.hovered ? theme.colorText : theme.colorBorder
                            border.width: 1.5
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Behavior on border.color { ColorAnimation { duration: 120 } }
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
                    height: 52
                    enabled: !bridge.busy
                    hoverEnabled: true
                    text: bridge.busy ? "Signing in…" : "Sign In →"
                    onClicked: root.requestSubmit()
                    scale: pressed ? 0.97 : 1.0
                    Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }

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
                        font.pixelSize: 18
                        font.bold: true
                        font.family: theme.fontSans
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        opacity: 1

                        // Password verification (bcrypt) takes a real,
                        // noticeable moment (see LoginBridge.submit's own
                        // comment on why `busy` exists at all) - without
                        // this, "Signing in..." is just a static label
                        // sitting there with no sign the app is actually
                        // doing anything, which is the exact "feels
                        // static/dead" complaint this whole animation
                        // pass is fixing.
                        SequentialAnimation on opacity {
                            running: bridge.busy
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.55; duration: 500; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1.0; duration: 500; easing.type: Easing.InOutSine }
                        }
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
                        font.pixelSize: 14
                        font.family: theme.fontSans
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                    }
                }

                Item { width: 1; height: 6 }

                // Reworded (2026-09-25): "Locked out" and "system
                // administrator" are the accurate technical terms but
                // read as jargon to a non-technical forecourt user -
                // "Can't sign in?" and "the person who manages this
                // computer" say the same thing in words a first-time
                // user is more likely to already understand.
                Text {
                    width: parent.width
                    text: "Can't sign in? Ask the person who manages this computer for help."
                    color: theme.colorTextFaint
                    font.pixelSize: 14
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
                shakeAnimation.start()
            }
        }
    }

    Component.onCompleted: usernameField.forceActiveFocus()
}
