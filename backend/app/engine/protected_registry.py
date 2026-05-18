from __future__ import annotations

import re
from functools import lru_cache

"""
Central guardrails for Performance mode (suspend/resume).

Separate from ML and cleanup. Browsers are never touched unless the user lists them explicitly.
"""

# Background helpers that may be suspended only when no explicit filter is used,
# or when explicitly named. Must never include browsers or security binaries.
DEFAULT_SOFT_SUSPEND_BASE_NAMES: frozenset[str] = frozenset(
    {
        "onedrive.exe",
        "dropbox.exe",
        "googledrivefs.exe",
        "creative cloud.exe",
        "adobeipcbroker.exe",
        "epicwebhelper.exe",
        "steamwebhelper.exe",
    }
)

# Suspend only if user explicitly lists these (typical browser / shell binaries).
BROWSER_OR_SHELL_BASE_NAMES: frozenset[str] = frozenset(
    {
        "chrome.exe",
        "msedge.exe",
        "brave.exe",
        "firefox.exe",
        "opera.exe",
        "vivaldi.exe",
        "iexplore.exe",
        "waterfox.exe",
        "zen.exe",  # optional future browser
        "explorer.exe",
    }
)

# Hard deny: OS, security, drivers, anticheat, networking stacks, input, AV.
_PROTECTED_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Windows core / session
    re.compile(r"^(csrss|smss|wininit|services|lsass|svchost|system|secure system)\.exe$", re.I),
    re.compile(r"^(winlogon|fontdrvhost|dwm|sihost|taskhostw|userinit|init\.exe)\.exe$", re.I),
    re.compile(r"^(runtimebroker|dllhost|mmc|rdpclip|sihost|logonui)\.exe$", re.I),
    # Security / AV
    re.compile(
        r"(?i)antimalware|defender|msmpeng|securityhealth|smartscreen|"
        r"sentinel|crowdstrike|carbon|cybereason|mssense|bdagent|avast|avg|mcshield|"
        r"kaspersky|eset|bitdefender|sophos|symantec|trellix|elastic-endpoint|f-secure"
    ),
    # Anticheat
    re.compile(r"(?i)easyanti|battleye|vac|nprotect|xigncode|punkbuster|fvanticheat"),
    # GPU / display
    re.compile(
        r"(?i)nvd?display|nvcontainer|nvidia|nvbackend|amdow|atieclxx|radeon|"
        r"igfx|intelgfx|graphics|gpuenergy"
    ),
    # Audio
    re.compile(r"(?i)audiodg|rtkaud|realtek|nahimic|dolby|krisp|sonic studio"),
    # Networking / wireless
    re.compile(r"(?i)wlanext|panther|iphelper|nslookup|wireless|wifinetworkmanager"),
    # Main Steam client (game library launcher — keep running)
    re.compile(r"(?i)^steam\.exe$"),
    # Input / accessibility
    re.compile(r"(?i)ctfmon|tabtip|textinputhost|wisptis|osk\.exe|speechruntime"),
    # Update / servicing that can brick sessions if mishandled
    re.compile(r"(?i)wuauclt|usoclient|trustedinstaller|tiworker|setuphost|servicing"),
    re.compile(r"(?i)lsass|csrss|rpcss"),
)

_CORE_SERVICE_NAMES: frozenset[str] = frozenset(
    {
        "rpcss",
        "samss",
        "schedule",
        "windefend",
        "mpssvc",
        "bfe",
        "dhcp",
        "dnscache",
        "nlasvc",
        "netman",
        "netprofm",
        "nsi",
        "w32time",
        "cryptsvc",
        "lanmanserver",
        "lanmanworkstation",
        "iphlpsvc",
        "dps",
        "diagtrack",
        "winmgmt",
        "wersvc",
    }
)


def _basename(name: str) -> str:
    return (name or "").replace("/", "\\").split("\\")[-1].strip()


def is_browser_or_shell_executable(name: str) -> bool:
    return _basename(name).lower() in BROWSER_OR_SHELL_BASE_NAMES


def is_hard_protected_process(name: str) -> bool:
    base = _basename(name)
    return any(p.search(base) for p in _PROTECTED_PATTERNS)


def is_protected_windows_service(service_name: str) -> bool:
    s = (service_name or "").strip().lower()
    if s in _CORE_SERVICE_NAMES:
        return True
    return bool(
        re.search(
            r"(audio|defend|firewall|mpssvc|rpc|samss|crypt|wudf|bth|hidserv|wlan|sched)",
            s,
            re.I,
        )
    )


def suspend_allowed_by_policy(
    process_name: str,
    *,
    explicit_target_basenames: frozenset[str],
) -> tuple[bool, str]:
    """
    Whether Performance mode may suspend this process name.

    explicit_target_basenames: lowercased basenames (e.g. {"spotify.exe"}).
    When empty, only DEFAULT_SOFT_SUSPEND_BASE_NAMES are eligible (non-browser).
    When non-empty, only processes in this set are eligible (plus policy checks).
    """
    base = _basename(process_name).lower()
    if not base:
        return False, "empty name"

    if is_hard_protected_process(process_name):
        return False, "hard-protected (OS, security, driver, network, or input stack)"

    if is_browser_or_shell_executable(process_name):
        if base not in explicit_target_basenames:
            return False, "browser/shell requires explicit user selection"
        return True, "explicitly targeted browser/shell"

    if explicit_target_basenames:
        if base not in explicit_target_basenames:
            return False, "not in user explicit target list"
        return True, "explicit target"

    if base in DEFAULT_SOFT_SUSPEND_BASE_NAMES:
        return True, "default soft-suspend allowlist"

    return False, "not in default allowlist (run preview with explicit targets to include)"


@lru_cache(maxsize=1)
def protected_pattern_count() -> int:
    return len(_PROTECTED_PATTERNS) + len(_CORE_SERVICE_NAMES) + len(BROWSER_OR_SHELL_BASE_NAMES)
