import UIKit
import Capacitor

@objc(BridgeViewController)
public class BridgeViewController: CAPBridgeViewController {
    public override func capacitorDidLoad() {
        // Explicit registration (works even if packageClassList is wiped by cap sync).
        bridge?.registerPluginInstance(CanvasLoginPlugin())
        bridge?.registerPluginInstance(HandwritingPlugin())
    }
}
