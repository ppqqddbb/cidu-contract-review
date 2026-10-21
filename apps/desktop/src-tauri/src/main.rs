#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn start_backend() -> Option<std::process::Child> {
    let Ok(executable) = std::env::current_exe() else {
        return None;
    };
    let Some(directory) = executable.parent() else {
        return None;
    };
    let backend = directory.join("contract-backend.exe");
    if !backend.is_file() {
        return None;
    }

    let mut command = std::process::Command::new(backend);
    let api_host = std::env::var("API_HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let api_port = std::env::var("API_PORT").unwrap_or_else(|_| "8000".to_string());
    command
        .current_dir(directory)
        .env("API_HOST", api_host)
        .env("API_PORT", api_port)
        .env("API_RELOAD", "false")
        .env("LIBREOFFICE_PATH", directory.join("libreoffice"));

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    command.spawn().ok()
}

fn main() {
    let backend_pid = start_backend().map(|child| child.id());
    contract_review_desktop_lib::run(backend_pid);
}
