#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      #[cfg(target_os = "windows")]
      {
        use tauri::Manager;
        use window_vibrancy::apply_mica;
        let window = app.get_webview_window("main").unwrap();
        // apply_mica requires Windows 11. 
        let _ = apply_mica(&window, None);
      }
      
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
