#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// macOS/dev-checkout-only backend sidecar spawn prototype. Not verified on
// Windows or Linux, and not wired into packaged-app resource bundling yet
// (see docs/PACKAGING.md, docs/TAURI_SIDECAR_READINESS_AUDIT.md).

use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};

#[cfg(unix)]
use signal_hook::consts::{SIGINT, SIGTERM};
#[cfg(unix)]
use signal_hook::iterator::Signals;

const HEALTH_ADDR: &str = "127.0.0.1:8742";
const HEALTH_PATH: &str = "/health";
const HEALTH_CHECK_TIMEOUT: Duration = Duration::from_millis(500);
const HEALTH_WAIT_ATTEMPTS: u32 = 20;
const HEALTH_WAIT_DELAY: Duration = Duration::from_millis(250);

struct SidecarChild(Mutex<Option<Child>>);

enum SpawnDecision {
    AlreadyRunning,
    ShouldSpawn,
}

fn decide(health_ok: bool) -> SpawnDecision {
    if health_ok {
        SpawnDecision::AlreadyRunning
    } else {
        SpawnDecision::ShouldSpawn
    }
}

fn check_health(timeout: Duration) -> bool {
    let addr = match HEALTH_ADDR.parse() {
        Ok(addr) => addr,
        Err(_) => return false,
    };
    let mut stream = match TcpStream::connect_timeout(&addr, timeout) {
        Ok(stream) => stream,
        Err(_) => return false,
    };
    if stream.set_read_timeout(Some(timeout)).is_err() {
        return false;
    }
    let request = format!("GET {HEALTH_PATH} HTTP/1.1\r\nHost: {HEALTH_ADDR}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")
}

fn wait_for_health(attempts: u32, delay: Duration) -> bool {
    for attempt in 0..attempts {
        if check_health(HEALTH_CHECK_TIMEOUT) {
            return true;
        }
        if attempt + 1 < attempts {
            std::thread::sleep(delay);
        }
    }
    false
}

/// Pure path join, no filesystem access — kept separate from
/// `backend_binary_path` so it's testable without a real checkout.
fn resolve_backend_binary(repo_root: &Path) -> PathBuf {
    repo_root.join("backend").join("dist").join("opencleaner-backend")
}

fn backend_binary_path() -> Option<PathBuf> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")); // frontend/src-tauri
    let repo_root = manifest_dir.parent()?.parent()?; // frontend -> repo root
    let candidate = resolve_backend_binary(repo_root);
    candidate.is_file().then_some(candidate)
}

fn sidecar_log_path() -> Option<PathBuf> {
    let home = std::env::var_os("HOME")?;
    let dir = PathBuf::from(home).join(".opencleaner").join("logs");
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir.join("sidecar.log"))
}

/// The PyInstaller `--onefile` backend binary forks a worker process and the
/// bootloader we spawn just supervises it; `Child::kill()` (SIGKILL) can't be
/// caught, so it kills only the bootloader and orphans the worker still
/// bound to the port. A real SIGTERM lets the bootloader forward the signal
/// to its worker; if it hasn't exited within the bound, fall back to kill().
#[cfg(unix)]
fn terminate_child(child: &mut Child) {
    let _ = Command::new("kill").arg("-TERM").arg(child.id().to_string()).status();
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    while std::time::Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) | Err(_) => return,
            Ok(None) => std::thread::sleep(Duration::from_millis(100)),
        }
    }
    let _ = child.kill();
}

#[cfg(not(unix))]
fn terminate_child(child: &mut Child) {
    let _ = child.kill();
}

/// Kills only the child stored in `state`, if any. Returns whether a stored
/// child was actually present and killed — a pre-existing backend Tauri
/// never spawned is never touched, since it was never stored here.
fn kill_tracked_child(state: &SidecarChild) -> bool {
    let Some(mut child) = state.0.lock().unwrap().take() else {
        return false;
    };
    terminate_child(&mut child);
    let _ = child.wait();
    true
}

fn spawn_backend(binary: &Path) -> Option<Child> {
    let mut command = Command::new(binary);
    match sidecar_log_path()
        .and_then(|path| std::fs::File::create(&path).ok())
        .and_then(|log_file| log_file.try_clone().ok().map(|stderr_file| (log_file, stderr_file)))
    {
        Some((stdout_file, stderr_file)) => {
            command.stdout(Stdio::from(stdout_file)).stderr(Stdio::from(stderr_file));
        }
        None => {
            command.stdout(Stdio::null()).stderr(Stdio::null());
        }
    }
    command.spawn().ok()
}

fn main() {
    tauri::Builder::default()
        .manage(SidecarChild(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle();
            std::thread::spawn(move || match decide(check_health(HEALTH_CHECK_TIMEOUT)) {
                SpawnDecision::AlreadyRunning => {
                    eprintln!("[sidecar] backend already responding on {HEALTH_ADDR}, not spawning");
                }
                SpawnDecision::ShouldSpawn => {
                    let Some(binary) = backend_binary_path() else {
                        eprintln!(
                            "[sidecar] {HEALTH_ADDR}{HEALTH_PATH} unreachable and no backend binary found at backend/dist/opencleaner-backend; relying on frontend readiness gate"
                        );
                        return;
                    };
                    let Some(child) = spawn_backend(&binary) else {
                        eprintln!("[sidecar] failed to spawn {}", binary.display());
                        return;
                    };
                    *handle.state::<SidecarChild>().0.lock().unwrap() = Some(child);
                    if wait_for_health(HEALTH_WAIT_ATTEMPTS, HEALTH_WAIT_DELAY) {
                        eprintln!("[sidecar] backend became healthy");
                    } else {
                        eprintln!("[sidecar] backend did not become healthy within bound; frontend readiness gate will report unreachable");
                    }
                }
            });

            // SIGTERM/SIGINT (e.g. a killed/force-quit parent process) bypass
            // Tauri's windowing event loop entirely, so `RunEvent::ExitRequested`
            // never fires for them — without this, a backend child spawned above
            // is orphaned. Unix-only: matches the macOS/dev-checkout scope of the
            // rest of this spawn prototype. Does not cover SIGKILL, crashes, or
            // power loss, which cannot be caught by any userspace handler.
            #[cfg(unix)]
            {
                let signal_handle = app.handle();
                if let Ok(mut signals) = Signals::new([SIGTERM, SIGINT]) {
                    std::thread::spawn(move || {
                        if let Some(sig) = signals.forever().next() {
                            let killed = kill_tracked_child(signal_handle.state::<SidecarChild>().inner());
                            eprintln!("[sidecar] received signal {sig}, killed_child={killed}, exiting");
                            std::process::exit(128 + sig);
                        }
                    });
                } else {
                    eprintln!("[sidecar] failed to register SIGTERM/SIGINT handler; termination signals will orphan a spawned backend");
                }
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                kill_tracked_child(app_handle.state::<SidecarChild>().inner());
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_backend_binary_joins_repo_root() {
        let resolved = resolve_backend_binary(Path::new("/repo"));
        assert_eq!(resolved, PathBuf::from("/repo/backend/dist/opencleaner-backend"));
    }

    #[test]
    fn decide_spawns_only_when_health_check_fails() {
        assert!(matches!(decide(false), SpawnDecision::ShouldSpawn));
        assert!(matches!(decide(true), SpawnDecision::AlreadyRunning));
    }

    #[test]
    fn kill_tracked_child_returns_false_when_none_stored() {
        let state = SidecarChild(Mutex::new(None));
        assert!(!kill_tracked_child(&state));
    }
}
