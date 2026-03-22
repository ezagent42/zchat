# VHS tape for recording E2E test execution
# Usage: vhs tests/e2e/e2e-test.tape

Output tests/e2e/e2e-test.gif

Require bash
Require weechat
Require claude
Require tmux
Require zenohd

Set Shell "bash"
Set FontSize 14
Set FontFamily "JetBrains Mono"
Set Width 1400
Set Height 800
Set Padding 10
Set TypingSpeed 30ms
Set PlaybackSpeed 3

Type "# WeeChat-Claude E2E Test Suite"
Enter
Sleep 1s

Type "bash tests/e2e/e2e-test.sh"
Enter

# E2E tests take several minutes — fast-forward wait periods
Sleep 300s
