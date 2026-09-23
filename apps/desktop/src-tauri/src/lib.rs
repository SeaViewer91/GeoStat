mod engine;

use engine::{Engine, EngineInfo};
use tauri::Manager;

/// 프론트엔드가 엔진 주소·토큰을 얻는 명령. 엔진이 준비될 때까지 기다림
#[tauri::command]
async fn engine_info(engine: tauri::State<'_, Engine>) -> Result<EngineInfo, String> {
    engine.info().await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // RUST_LOG로 조절 가능. 기본은 info 수준을 stderr로 출력함
    let _ = env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .try_init();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // 창이 뜨는 동안 엔진을 병렬로 띄움
            let engine = Engine::start(app.handle());
            app.manage(engine);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![engine_info])
        .build(tauri::generate_context!())
        .expect("GeoStat 앱을 초기화하지 못함")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                app.state::<Engine>().shutdown();
            }
        });
}
