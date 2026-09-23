// 릴리스 빌드에서 Windows 콘솔 창이 뜨지 않게 함 (macOS에는 영향 없음)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    geostat_lib::run()
}
