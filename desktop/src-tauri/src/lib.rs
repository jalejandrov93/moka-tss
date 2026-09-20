use tauri::{
    menu::MenuBuilder,
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, WindowEvent,
};
use tauri_plugin_shell::{process::CommandEvent, ShellExt};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app
                .get_webview_window("main")
                .or_else(|| app.webview_windows().into_values().next())
            {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let (mut rx, _child) = app
                .shell()
                .sidecar("moka-sidecar")?
                .args(["--no-tray"])
                .spawn()?;

            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                let _child = _child;
                while let Some(event) = rx.blocking_recv() {
                    match event {
                        CommandEvent::Stdout(line_bytes) => {
                            let text = String::from_utf8_lossy(&line_bytes);
                            for line in text.lines() {
                                let trimmed = line.trim();
                                if let Some(rest) = trimmed.strip_prefix("MOKA_READY port=") {
                                    if let Ok(port) = rest.trim().parse::<u16>() {
                                        let _ = app_handle.emit("moka-sidecar-ready", port);
                                    }
                                }
                            }
                        }
                        CommandEvent::Terminated(_) => {
                            let _ = app_handle.emit("moka-sidecar-crashed", ());
                        }
                        _ => {}
                    }
                }
            });

            let tray_menu = MenuBuilder::new(app)
                .text("open", "Abrir Mascota")
                .separator()
                .text("pause", "Pausar monitoreo")
                .text("restart", "Reiniciar servicios")
                .separator()
                .text("quit", "Salir")
                .build()?;

            TrayIconBuilder::new()
                .icon(tauri::include_image!("icons/32x32.png"))
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "open" => {
                            if let Some(window) = app
                                .get_webview_window("main")
                                .or_else(|| app.webview_windows().into_values().next())
                            {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                            }
                        }
                        "pause" => {
                            let _ = app.emit("moka-pause", ());
                        }
                        "restart" => {
                            let _ = app.emit("moka-restart-services", ());
                        }
                        "quit" => {
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app
                            .get_webview_window("main")
                            .or_else(|| app.webview_windows().into_values().next())
                        {
                            let is_visible = window.is_visible().unwrap_or(false);
                            if is_visible {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

