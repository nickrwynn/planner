import UIKit
import Capacitor
import CapApp_SPM

open class BridgeViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(CanvasLoginPlugin())
    }
}
