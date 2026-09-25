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

    // PIN vs password sign-in mode: a plain QML property, toggled only
    // by direct assignment in a click handler (pure QML/JS, the same
    // safe pattern as submitTrigger) - LoginWindow.py connects this
    // property's own auto-generated changed signal to
    // bridge.setPinMode via a Qt.QueuedConnection, so Python only ever
    // learns the new mode after the click has fully finished.
    property bool pinMode: false

    // "Forgot password?" - same queued-trigger pattern as submitTrigger,
    // since opening a dialog is itself a call into Python that must not
    // happen synchronously from inside a live click.
    property int forgotPasswordTrigger: 0
    function requestForgotPassword() { forgotPasswordTrigger++ }

    // Same queued-trigger pattern again for the theme toggle - it was
    // initially wired as a direct `onClicked: bridge.toggleDarkMode()`
    // call, which is exactly the unsafe pattern submitTrigger's own long
    // comment exists to warn against (a Slot call from a live click),
    // caught on review before it shipped.
    property int themeToggleTrigger: 0
    function requestThemeToggle() { themeToggleTrigger++ }

    // Login-screen-only language switch (2026-09-25, scoped deliberately
    // narrow per user decision): covers this one screen's own strings,
    // not the rest of the app - full app-wide i18n (Qt Linguist .ts/.qm
    // files for every screen) is a separate, much larger infrastructure
    // project, out of scope here. bridge.initialLoginLocale is read once
    // at construction (a `constant` Property); every change after that
    // lives entirely in this QML property, reported back to Python only
    // to persist it (see LoginBridge.setLoginLocale).
    property string loginLocale: bridge.initialLoginLocale

    readonly property var _en: ({
        welcomeBack: "Welcome back",
        usernameLabel: "Username",
        usernamePlaceholder: "Enter your username",
        passwordLabel: "Password",
        pinLabel: "PIN",
        passwordPlaceholder: "Your password",
        pinPlaceholder: "6-digit PIN",
        signIn: "Sign In →",
        signingIn: "Signing in…",
        usePinInstead: "Use PIN instead",
        usePasswordInstead: "Use password instead",
        cantSignIn: "Can't sign in? Ask the person who manages this computer for help.",
        forgotPassword: "Forgot password?",
        show: "Show",
        hide: "Hide",
        usernameRequired: "Username is required.",
        passwordRequired: "Password is required.",
        pinRequired: "PIN is required.",
        capsLockOn: "Caps Lock is on."
    })

    readonly property var _hi: ({
        welcomeBack: "वापसी पर स्वागत है",
        usernameLabel: "उपयोगकर्ता नाम",
        usernamePlaceholder: "अपना उपयोगकर्ता नाम डालें",
        passwordLabel: "पासवर्ड",
        pinLabel: "पिन",
        passwordPlaceholder: "अपना पासवर्ड डालें",
        pinPlaceholder: "6 अंकों का पिन",
        signIn: "साइन इन करें →",
        signingIn: "साइन इन हो रहा है…",
        usePinInstead: "इसके बजाय पिन का उपयोग करें",
        usePasswordInstead: "इसके बजाय पासवर्ड का उपयोग करें",
        cantSignIn: "साइन इन नहीं कर पा रहे? इस कंप्यूटर का प्रबंधन करने वाले व्यक्ति से मदद लें।",
        forgotPassword: "पासवर्ड भूल गए?",
        show: "दिखाएं",
        hide: "छुपाएं",
        usernameRequired: "उपयोगकर्ता नाम आवश्यक है।",
        passwordRequired: "पासवर्ड आवश्यक है।",
        pinRequired: "पिन आवश्यक है।",
        capsLockOn: "कैप्स लॉक ऑन है।"
    })

    readonly property var strings: loginLocale === "hi" ? _hi : _en

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

    // Seeded from bridge.lockoutSecondsRemaining (see the Connections
    // block below) and ticked down locally by lockoutCountdownTimer -
    // kept as its own root property rather than binding straight to
    // bridge.lockoutSecondsRemaining, since that value is only ever
    // computed once per failed attempt and would otherwise stay frozen
    // at whatever it was first set to instead of counting down.
    property int lockoutSecondsLeft: 0

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

        // Utility row: an offline badge (this app never needs or uses an
        // internet connection, matching the same static badge the main
        // window's own top bar shows post-login - see MainWindow's
        // offline_indicator_label) and a theme toggle, so light/dark mode
        // can be set before signing in rather than only afterwards. Plain
        // anchors, not a Layout - this file only imports QtQuick/
        // QtQuick.Controls.Basic, not QtQuick.Layouts.
        Item {
            width: root.formWidth
            height: Math.max(offlineBadge.implicitHeight, themeToggle.height)

            Text {
                id: offlineBadge
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: "● Offline — Local Only"
                color: theme.colorTextFaint
                font.pixelSize: 12
                font.family: theme.fontSans
            }

            Button {
                id: localeToggle
                objectName: "localeToggleButton"
                anchors.right: themeToggle.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                focusPolicy: Qt.NoFocus
                hoverEnabled: true
                text: root.loginLocale === "hi" ? "EN" : "हिं"
                font.pixelSize: 12
                font.family: theme.fontSans
                height: 28
                onClicked: root.loginLocale = (root.loginLocale === "hi" ? "en" : "hi")
                HoverHandler { cursorShape: Qt.PointingHandCursor }

                background: Rectangle {
                    radius: theme.radiusFull
                    color: localeToggle.hovered ? theme.colorBg : "transparent"
                    border.color: theme.colorBorder
                    border.width: 1
                }
                contentItem: Text {
                    text: localeToggle.text
                    color: theme.colorTextMuted
                    font: localeToggle.font
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 10
                    rightPadding: 10
                }
            }

            Button {
                id: themeToggle
                objectName: "themeToggleButton"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                focusPolicy: Qt.NoFocus
                hoverEnabled: true
                text: bridge.darkMode ? "☀ Light" : "☾ Dark"
                font.pixelSize: 12
                font.family: theme.fontSans
                height: 28
                onClicked: root.requestThemeToggle()
                HoverHandler { cursorShape: Qt.PointingHandCursor }

                background: Rectangle {
                    radius: theme.radiusFull
                    color: themeToggle.hovered ? theme.colorBg : "transparent"
                    border.color: theme.colorBorder
                    border.width: 1
                }
                contentItem: Text {
                    text: themeToggle.text
                    color: theme.colorTextMuted
                    font: themeToggle.font
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: 10
                    rightPadding: 10
                }
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

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "This device: " + bridge.deviceName
                color: theme.colorTextFaint
                font.pixelSize: 12
                font.family: theme.fontSans
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
                    text: root.strings.welcomeBack
                    font.pixelSize: 26
                    font.bold: true
                    font.family: theme.fontSans
                    color: theme.colorText
                }

                Item { width: 1; height: 8 }

                Text {
                    text: root.strings.usernameLabel
                    font.pixelSize: 16
                    font.bold: true
                    font.family: theme.fontSans
                    color: theme.colorTextMuted
                }

                // Recently-used usernames on this specific terminal (see
                // app/ui/terminal_settings.py) - a shared forecourt PC is
                // used by a handful of people across shifts, so a tap
                // fills the field instead of retyping a name that was
                // just used here an hour ago. Only the username is
                // remembered, never a password/PIN, so this carries no
                // credential of its own.
                Flow {
                    width: parent.width
                    spacing: 8
                    visible: bridge.recentUsernames.length > 0

                    Repeater {
                        model: bridge.recentUsernames
                        delegate: Button {
                            required property string modelData
                            objectName: "recentUsernameChip"
                            focusPolicy: Qt.NoFocus
                            hoverEnabled: true
                            text: modelData
                            font.pixelSize: 13
                            font.family: theme.fontSans
                            height: 30
                            onClicked: {
                                usernameField.text = modelData
                                passwordField.forceActiveFocus()
                            }
                            HoverHandler { cursorShape: Qt.PointingHandCursor }

                            background: Rectangle {
                                radius: theme.radiusFull
                                color: parent.hovered ? theme.colorBg : theme.colorSurface
                                border.color: theme.colorBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: parent.text
                                color: theme.colorTextMuted
                                font: parent.font
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 10
                                rightPadding: 10
                            }
                        }
                    }
                }

                TextField {
                    id: usernameField
                    objectName: "usernameField"
                    width: parent.width
                    height: 52
                    placeholderText: root.strings.usernamePlaceholder
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

                    // Inline validation (2026-09-25 follow-up): a hint the
                    // moment the user leaves this field empty, rather than
                    // only after a whole submit attempt fails - property
                    // set only on blur, never while still typing, so it
                    // doesn't nag before the user has even had a chance to
                    // type anything.
                    property bool touched: false
                    onActiveFocusChanged: if (!activeFocus) touched = true

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
                    text: root.strings.usernameRequired
                    visible: usernameField.touched && usernameField.text.length === 0
                    color: theme.colorDanger
                    font.pixelSize: 13
                    font.family: theme.fontSans
                }

                Item {
                    width: parent.width
                    height: pinModeLabel.implicitHeight

                    Text {
                        id: pinModeLabel
                        anchors.left: parent.left
                        text: root.pinMode ? root.strings.pinLabel : root.strings.passwordLabel
                        font.pixelSize: 16
                        font.bold: true
                        font.family: theme.fontSans
                        color: theme.colorTextMuted
                    }

                    // PIN vs password toggle (2026-09-25): quick-sign-in
                    // PIN is opt-in and self-service (see
                    // app/ui/set_pin_dialog.py) - a returning user who set
                    // one up can switch here instead of always typing a
                    // full password. Pure QML property flip, no Python
                    // call from this click (see root.pinMode's own
                    // comment).
                    Text {
                        id: modeToggleLink
                        objectName: "pinModeToggleLink"
                        anchors.right: parent.right
                        text: root.pinMode ? root.strings.usePasswordInstead : root.strings.usePinInstead
                        color: theme.colorPrimary
                        font.pixelSize: 13
                        font.family: theme.fontSans
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.pinMode = !root.pinMode
                        }
                    }
                }

                Row {
                    width: parent.width
                    spacing: 8
                    visible: !root.pinMode

                    TextField {
                        id: passwordField
                        objectName: "passwordField"
                        width: parent.width - toggleButton.width - 8
                        height: 52
                        placeholderText: root.strings.passwordPlaceholder
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
                        property bool touched: false
                        onActiveFocusChanged: {
                            if (!activeFocus) {
                                toggleButton.checked = false
                                touched = true
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
                        text: checked ? root.strings.hide : root.strings.show
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

                TextField {
                    id: pinField
                    objectName: "pinField"
                    visible: root.pinMode
                    width: parent.width
                    height: 52
                    placeholderText: root.strings.pinPlaceholder
                    font.pixelSize: 20
                    font.family: theme.fontSans
                    color: theme.colorText
                    leftPadding: 16
                    rightPadding: 16
                    selectByMouse: true
                    hoverEnabled: true
                    echoMode: TextInput.Password
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: RegularExpressionValidator { regularExpression: /^[0-9]{0,6}$/ }
                    onAccepted: root.requestSubmit()
                    onTextChanged: if (root.pinMode) bridge.pin = text

                    property bool touched: false
                    onActiveFocusChanged: if (!activeFocus) touched = true

                    background: Rectangle {
                        radius: theme.radiusMd
                        color: theme.colorSurface
                        border.color: pinField.activeFocus
                            ? theme.colorText
                            : (pinField.hovered ? theme.colorTextMuted : theme.colorBorder)
                        border.width: pinField.activeFocus ? 2 : 1.5
                        Behavior on border.color { ColorAnimation { duration: 120 } }
                        Behavior on border.width { NumberAnimation { duration: 120 } }
                    }
                }

                Text {
                    text: root.strings.passwordRequired
                    visible: !root.pinMode && passwordField.touched && passwordField.text.length === 0
                    color: theme.colorDanger
                    font.pixelSize: 13
                    font.family: theme.fontSans
                }

                Text {
                    text: root.strings.pinRequired
                    visible: root.pinMode && pinField.touched && pinField.text.length === 0
                    color: theme.colorDanger
                    font.pixelSize: 13
                    font.family: theme.fontSans
                }

                // Caps Lock warning (2026-09-25 follow-up): the single
                // highest-value, lowest-effort login fix per the client
                // review's own punch list - most "wrong password" support
                // requests trace back to this, and it costs nothing to
                // check once the state is available (see
                // app/core/keyboard_state.py / LoginBridge.capsLockOn).
                // Shown whenever Caps Lock is on, not just while a field
                // has focus, since it affects both fields identically.
                Row {
                    width: parent.width
                    spacing: 6
                    visible: bridge.capsLockOn

                    Text {
                        text: "⚠"
                        color: theme.colorDanger
                        font.pixelSize: 13
                    }
                    Text {
                        text: root.strings.capsLockOn
                        color: theme.colorDanger
                        font.pixelSize: 13
                        font.family: theme.fontSans
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
                    text: bridge.busy ? root.strings.signingIn : root.strings.signIn
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

                // Attempts-remaining / lockout countdown (2026-09-25
                // follow-up): AuthService.authenticate already computed
                // and enforced this - see the lockout warning that used
                // to say only "wait 15 minutes" with no visible sense of
                // how much of that was left, and the wrong-password error
                // that gave no hint how close the account was to locking.
                // secondsLeft ticks down locally once a second rather
                // than re-querying Python every second - it's only ever
                // seeded from bridge.lockoutSecondsRemaining, right after
                // a failed attempt.
                Text {
                    width: parent.width
                    visible: root.lockoutSecondsLeft > 0
                    text: "Try again in " + Math.floor(root.lockoutSecondsLeft / 60) + ":" +
                          String(root.lockoutSecondsLeft % 60).padStart(2, "0")
                    color: theme.colorDanger
                    font.pixelSize: 13
                    font.bold: true
                    font.family: theme.fontSans
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    width: parent.width
                    visible: root.lockoutSecondsLeft === 0 && bridge.attemptsRemaining >= 0 && bridge.attemptsRemaining <= 3
                    text: bridge.attemptsRemaining === 1
                        ? "1 attempt remaining before this account is locked."
                        : bridge.attemptsRemaining + " attempts remaining before this account is locked."
                    color: theme.colorTextMuted
                    font.pixelSize: 13
                    font.family: theme.fontSans
                    horizontalAlignment: Text.AlignHCenter
                }

                Timer {
                    id: lockoutCountdownTimer
                    interval: 1000
                    repeat: true
                    running: root.lockoutSecondsLeft > 0
                    onTriggered: root.lockoutSecondsLeft = Math.max(0, root.lockoutSecondsLeft - 1)
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
                    text: root.strings.cantSignIn
                    color: theme.colorTextFaint
                    font.pixelSize: 14
                    font.family: theme.fontSans
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }

                Text {
                    id: forgotPasswordLink
                    objectName: "forgotPasswordLink"
                    width: parent.width
                    visible: !root.pinMode
                    text: root.strings.forgotPassword
                    color: theme.colorPrimary
                    font.pixelSize: 14
                    font.family: theme.fontSans
                    horizontalAlignment: Text.AlignHCenter
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.requestForgotPassword()
                    }
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
                if (root.pinMode) {
                    pinField.text = ""
                    pinField.forceActiveFocus()
                } else {
                    passwordField.text = ""
                    passwordField.forceActiveFocus()
                }
                shakeAnimation.start()
            }
        }
        function onLockoutSecondsRemainingChanged() {
            root.lockoutSecondsLeft = bridge.lockoutSecondsRemaining
        }
    }

    // Caps Lock polling (see LoginBridge.pollCapsLock's own docstring for
    // why this timer lives here, in QML, rather than as a Python-owned
    // QTimer inside LoginBridge itself): this Timer's lifetime is tied
    // to this scene, so it stops existing the moment LoginScreen.qml's
    // root item is destroyed - exactly when LoginWindow closes, with no
    // separate cleanup call needed. 400ms is fast enough to feel
    // immediate without being fast enough to matter performance-wise.
    Timer {
        interval: 400
        running: true
        repeat: true
        onTriggered: bridge.pollCapsLock()
    }

    Component.onCompleted: usernameField.forceActiveFocus()
}
