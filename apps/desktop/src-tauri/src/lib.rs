use std::{env, fs, path::PathBuf, process::Command};

fn stop_backend(backend_pid: Option<u32>) {
    let Some(pid) = backend_pid else {
        return;
    };

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;

        // Terminate the FastAPI process and any active LibreOffice children.
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(0x08000000)
            .status();
    }
}

fn report_downloads_dir() -> Result<PathBuf, String> {
    let home = env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .ok_or_else(|| "Unable to find the current user profile directory.".to_string())?;
    let downloads = home.join("Downloads");
    fs::create_dir_all(&downloads)
        .map_err(|error| format!("Unable to create the Downloads directory: {error}"))?;
    Ok(downloads)
}

fn safe_report_filename(filename: &str) -> String {
    let stem = filename
        .trim()
        .trim_end_matches(".txt")
        .trim_end_matches(".TXT")
        .chars()
        .map(|character| match character {
            '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*' => '_',
            _ => character,
        })
        .collect::<String>();
    let stem = stem.trim_matches('.').trim();
    let stem = if stem.is_empty() { "contract-review-report" } else { stem };
    format!("{}.txt", stem.chars().take(120).collect::<String>())
}

#[tauri::command]
fn save_review_report(filename: String, content: String) -> Result<String, String> {
    let directory = report_downloads_dir()?;
    let filename = safe_report_filename(&filename);
    let path = directory.join(&filename);
    let stem = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("contract-review-report")
        .to_owned();
    let mut destination = path;
    let mut index = 1;

    while destination.exists() {
        destination = directory.join(format!("{stem} ({index}).txt"));
        index += 1;
    }

    fs::write(&destination, format!("\u{feff}{content}"))
        .map_err(|error| format!("Unable to save the report: {error}"))?;
    Ok(destination.display().to_string())
}

#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    let url = url.trim();
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err("Only HTTP(S) links can be opened.".to_string());
    }

    Command::new("explorer.exe")
        .arg(url)
        .spawn()
        .map_err(|error| format!("Unable to open the link in the default browser: {error}"))?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run(backend_pid: Option<u32>) {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![save_review_report, open_external_url])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");
    app.run(move |_app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                stop_backend(backend_pid);
            }
        });
}
