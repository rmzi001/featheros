import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 8000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#111622"

            Column {
                anchors.centerIn: parent
                spacing: 14
                width: parent.width * 0.8

                Text {
                    text: "Welcome to FeatherOS 0.3.0"
                    color: "#f8fafc"
                    font.pixelSize: 28
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "A lightweight Windows 11-inspired desktop engineered for speed, low RAM usage, and effortless everyday computing."
                    color: "#cbd5e1"
                    font.pixelSize: 15
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                }
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#111622"

            Column {
                anchors.centerIn: parent
                spacing: 14
                width: parent.width * 0.8

                Text {
                    text: "Run Windows Apps with FeatherRun"
                    color: "#38bdf8"
                    font.pixelSize: 26
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "Double-click .exe and .msi installers directly in File Explorer. FeatherRun manages Wine bottles, DXVK acceleration, and Start Menu shortcuts automatically."
                    color: "#cbd5e1"
                    font.pixelSize: 15
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                }
            }
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#111622"

            Column {
                anchors.centerIn: parent
                spacing: 14
                width: parent.width * 0.8

                Text {
                    text: "Dark & Light Glass + FeatherStore"
                    color: "#34d399"
                    font.pixelSize: 26
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Text {
                    text: "Switch between Dark Glass and Light Glass in FeatherSettings, and install browsers, Steam, GE-Proton, Office, or dev tools in one click."
                    color: "#cbd5e1"
                    font.pixelSize: 15
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    width: parent.width
                }
            }
        }
    }
}
