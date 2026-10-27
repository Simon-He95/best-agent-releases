$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class GuiProbe {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr GetKeyboardLayout(uint id);
  [DllImport("user32.dll")] public static extern void keybd_event(byte key, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT rect);
  public struct RECT { public int Left,Top,Right,Bottom; }
}
'@
$binary = (Resolve-Path 'release/best-agent-0.0.18-beta.1-win32-x64/bin/best-agent.exe').Path
$homeDir = Join-Path $env:RUNNER_TEMP 'ime-gui-home'
New-Item -ItemType Directory -Force $homeDir | Out-Null
$provider = Join-Path $homeDir 'provider.json'
'{"kind":"openai","model":"fixture","apiKey":"fixture","baseURL":"http://127.0.0.1:1/v1","compatibilityMode":"compatible"}' | Set-Content -Encoding utf8 $provider
$env:DIMCODE_HOME = $homeDir
$env:DIMCODE_LANG = 'en'
$env:BEST_AGENT_PROVIDER_CONFIG = $provider
$env:BEST_AGENT_STORAGE_ROOT = Join-Path $homeDir 'storage'
$env:VUE_TUI_TERMINAL_GRAPHICS = 'none'
$wt = Get-AppxPackage Microsoft.WindowsTerminal
$window = Start-Process -FilePath (Join-Path $wt.InstallLocation 'WindowsTerminal.exe') -ArgumentList @('-w','new','--', $binary, 'chat') -PassThru
Start-Sleep -Seconds 12
$terminal = Get-Process WindowsTerminal | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object StartTime -Descending | Select-Object -First 1
if (!$terminal) { throw 'No Windows Terminal window found' }
$h = $terminal.MainWindowHandle
[GuiProbe]::ShowWindow($h,9) | Out-Null
[GuiProbe]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Seconds 2
function Snapshot($name) {
  $rect = New-Object GuiProbe+RECT
  [GuiProbe]::GetWindowRect($h,[ref]$rect) | Out-Null
  $width = $rect.Right - $rect.Left; $height = $rect.Bottom - $rect.Top
  if ($width -le 0 -or $height -le 0) { throw 'Window has no visible area' }
  $img = [Drawing.Bitmap]::new($width,$height)
  $g = [Drawing.Graphics]::FromImage($img)
  try { $g.CopyFromScreen($rect.Left,$rect.Top,0,0,$img.Size); $img.Save((Join-Path $env:GITHUB_WORKSPACE $name),[Drawing.Imaging.ImageFormat]::Png) }
  finally { $g.Dispose(); $img.Dispose() }
}
function Info($label) {
  $foreground = [GuiProbe]::GetForegroundWindow()
  [uint32]$processId=0
  $thread = [GuiProbe]::GetWindowThreadProcessId($foreground,[ref]$processId)
  Write-Output "$label foreground=$foreground terminal=$h pid=$processId keyboard=$([GuiProbe]::GetKeyboardLayout($thread))"
  if ($foreground -ne $h) { throw 'Terminal window did not receive focus; cannot validate input' }
}
Info 'before-chat'
[System.Windows.Forms.SendKeys]::SendWait('hello')
Start-Sleep -Seconds 1
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Seconds 12
Info 'chat-page'
Snapshot 'ime-chat-before.png'
[GuiProbe]::keybd_event(0x5B,0,0,[UIntPtr]::Zero)
[GuiProbe]::keybd_event(0x20,0,0,[UIntPtr]::Zero)
[GuiProbe]::keybd_event(0x20,0,2,[UIntPtr]::Zero)
[GuiProbe]::keybd_event(0x5B,0,2,[UIntPtr]::Zero)
Start-Sleep -Seconds 3
Info 'after-language-switch'
[System.Windows.Forms.SendKeys]::SendWait('nihao')
Start-Sleep -Seconds 2
Snapshot 'ime-chat-composition.png'
[System.Windows.Forms.SendKeys]::SendWait(' ')
Start-Sleep -Seconds 2
Snapshot 'ime-chat-commit.png'
Write-Output 'Screenshots are observational evidence only. Confirm Chinese IME activation and compare composition and committed text before interpreting.'
