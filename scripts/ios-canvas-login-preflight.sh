#!/usr/bin/env bash
# Preflight checks before archiving StudyFlows iOS for TestFlight.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/apps/web/ios/App/App"
PBX="$ROOT/apps/web/ios/App/App.xcodeproj/project.pbxproj"
STORYBOARD="$APP/Base.lproj/Main.storyboard"
PLUGIN="$APP/CanvasLoginPlugin.swift"
BRIDGE="$APP/BridgeViewController.swift"
CONFIG="$APP/capacitor.config.json"

fail() { echo "PREFLIGHT FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

test -f "$PLUGIN" || fail "missing $PLUGIN"
test -f "$BRIDGE" || fail "missing $BRIDGE"
test -f "$STORYBOARD" || fail "missing $STORYBOARD"
test -f "$PBX" || fail "missing $PBX"

grep -q 'jsName = "CanvasLogin"' "$PLUGIN" || fail "plugin jsName must be CanvasLogin"
grep -q 'loginAndCaptureSession' "$PLUGIN" || fail "plugin missing loginAndCaptureSession"
grep -q 'HTTPCookie.requestHeaderFields' "$PLUGIN" || fail "plugin must verify with requestHeaderFields"
grep -q 'usersSelfURL' "$PLUGIN" || fail "plugin must build /users/self URL without path-encoding bugs"
if grep -q 'appendingPathComponent("api/v1' "$PLUGIN"; then
  fail "plugin must not use appendingPathComponent for api/v1 paths"
fi
grep -q 'api/v1/users/self' "$PLUGIN" || fail "plugin must call /api/v1/users/self"
grep -q 'NSURLErrorCancelled' "$PLUGIN" || fail "plugin must ignore cancelled SSO redirects"
grep -q 'registerPluginInstance(CanvasLoginPlugin' "$BRIDGE" || fail "BridgeViewController must register CanvasLoginPlugin"
grep -q 'customClass="BridgeViewController"' "$STORYBOARD" || fail "Main.storyboard must use BridgeViewController"
grep -q 'CanvasLoginPlugin.swift in Sources' "$PBX" || fail "pbxproj must compile CanvasLoginPlugin.swift"
grep -q 'BridgeViewController.swift in Sources' "$PBX" || fail "pbxproj must compile BridgeViewController.swift"

# capacitor.config.json is often gitignored; after cap sync it must list the plugin.
if [[ -f "$CONFIG" ]]; then
  grep -q 'CanvasLoginPlugin' "$CONFIG" || fail "capacitor.config.json missing CanvasLoginPlugin in packageClassList"
  ok "capacitor.config.json lists CanvasLoginPlugin"
else
  echo "WARN: capacitor.config.json not present yet (expected before sync)"
fi

VERSION="$(grep -o 'CURRENT_PROJECT_VERSION = [0-9]*' "$PBX" | head -1 | awk '{print $3}')"
[[ -n "$VERSION" ]] || fail "could not read CURRENT_PROJECT_VERSION"
ok "CURRENT_PROJECT_VERSION=$VERSION"
ok "CanvasLogin iOS wiring looks correct"
