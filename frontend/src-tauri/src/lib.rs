use std::{
    net::{IpAddr, Ipv4Addr, SocketAddr, TcpStream},
    path::{Path, PathBuf},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const PREFERRED_SERVER_PORT: u16 = 8000;

#[derive(serde::Deserialize)]
struct Ready {
    port: u16,
}

struct Sidecar {
    child: Mutex<Option<CommandChild>>,
    ready_file: PathBuf,
}

fn wait_for_server(ready_file: &Path) -> Result<u16, Box<dyn std::error::Error>> {
    let deadline = Instant::now() + Duration::from_secs(20);
    while Instant::now() < deadline {
        if let Ok(contents) = std::fs::read_to_string(ready_file) {
            if let Ok(ready) = serde_json::from_str::<Ready>(&contents) {
                let address = SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), ready.port);
                if TcpStream::connect_timeout(&address, Duration::from_millis(200)).is_ok() {
                    return Ok(ready.port);
                }
            }
        }
        thread::sleep(Duration::from_millis(120));
    }
    Err("Pansy 本地服务未能在 20 秒内启动".into())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let sidecar_args = vec![
                "--host".to_string(),
                "127.0.0.1".to_string(),
                "--port".to_string(),
                PREFERRED_SERVER_PORT.to_string(),
                "--fallback-port".to_string(),
                "--parent-pid".to_string(),
                std::process::id().to_string(),
                "--ready-file".to_string(),
                std::env::temp_dir()
                    .join(format!("pansy-ready-{}.txt", std::process::id()))
                    .to_string_lossy()
                    .into_owned(),
            ];
            let ready_file = PathBuf::from(sidecar_args.last().unwrap());
            let _ = std::fs::remove_file(&ready_file);
            let sidecar = app
                .shell()
                .sidecar("pansy-server")?
                .args(sidecar_args);
            let (mut events, child) = sidecar.spawn()?;
            app.manage(Sidecar {
                child: Mutex::new(Some(child)),
                ready_file: ready_file.clone(),
            });

            // 持续读取 sidecar 事件，避免它的输出通道塞满后阻止服务继续运行。
            tauri::async_runtime::spawn(async move {
                while events.recv().await.is_some() {}
            });

            let server_port = wait_for_server(&ready_file)?;
            let url = format!("http://127.0.0.1:{server_port}").parse()?;
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("Pansy")
                .inner_size(1180.0, 760.0)
                .min_inner_size(900.0, 620.0)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("无法启动 Pansy 桌面应用");

    application.run(|handle, event| {
        if matches!(event, RunEvent::Exit) {
            let state = handle.state::<Sidecar>();
            if let Some(child) = state.child.lock().unwrap().take() {
                let _ = child.kill();
            }
            let _ = std::fs::remove_file(&state.ready_file);
        }
    });
}
