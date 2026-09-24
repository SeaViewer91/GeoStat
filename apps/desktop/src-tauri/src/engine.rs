//! Python 분석 엔진 프로세스 관리
//!
//! 앱 시작 시 엔진을 하위 프로세스로 띄우고, stdout의 준비 신호에서 포트를 읽어
//! 프론트엔드에 주소·토큰을 알려줌. 종료 시 stdin을 닫아 엔진이 스스로 끝나게 함.
//! 엔진이 도중에 죽으면 `engine-exited` 이벤트로 알리고, 프론트엔드가 `restart()`로 다시 띄울 수 있음.
//!
//! 엔진 실행 파일 탐색 순서
//!   1. 환경변수 GEOSTAT_ENGINE_URL 이 있으면 이미 떠 있는 엔진에 붙음 (디버깅용, 프로세스 안 띄움)
//!   2. 디버그 빌드: 저장소의 engine/ 폴더를 `uv run`으로 실행 (GEOSTAT_ENGINE_BUNDLED=1이면 건너뜀)
//!   3. 앱 번들 리소스의 engine/geostat-engine/geostat-engine (PyInstaller onedir 빌드)

use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
#[cfg(debug_assertions)]
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::watch;

const READY_PREFIX: &str = "GEOSTAT_ENGINE_READY ";
/// 첫 실행 시 PyInstaller 번들 압축 해제·임포트로 시간이 걸릴 수 있어 넉넉히 잡음
const START_TIMEOUT: Duration = Duration::from_secs(90);
/// 시작 실패 시 오류 메시지에 붙일 stderr 마지막 줄 수
const STDERR_TAIL_LINES: usize = 30;
/// 종료 요청 후 강제 종료까지 기다리는 시간
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);

/// 프론트엔드에 전달하는 연결 정보
#[derive(Clone, Debug, Serialize)]
pub struct EngineInfo {
    pub url: String,
    pub token: String,
}

#[derive(Clone, Debug)]
enum Status {
    Starting,
    Ready(EngineInfo),
    Failed(String),
}

#[derive(Deserialize)]
struct ReadyLine {
    port: u16,
}

/// 엔진이 준비된 뒤 종료됐을 때 프론트엔드로 보내는 이벤트 이름
pub const EXITED_EVENT: &str = "engine-exited";

pub struct Engine {
    app: AppHandle,
    tx: Arc<watch::Sender<Status>>,
    status: watch::Receiver<Status>,
    child: Mutex<Option<Child>>,
    /// 몇 번째로 띄운 엔진인지. 이전 엔진의 종료 알림이 새 엔진 상태를 덮어쓰지 않게 구분함
    generation: Arc<Mutex<u64>>,
}

impl Engine {
    /// 엔진을 시작함. 준비 완료를 기다리지 않고 즉시 반환하며, 결과는 `info()`로 받음
    pub fn start(app: &AppHandle) -> Self {
        let (tx, rx) = watch::channel(Status::Starting);
        let engine = Self {
            app: app.clone(),
            tx: Arc::new(tx),
            status: rx,
            child: Mutex::new(None),
            generation: Arc::new(Mutex::new(0)),
        };
        engine.launch();
        engine
    }

    /// 엔진을 종료하고 새로 띄움 (엔진이 죽었을 때 프론트엔드가 요청함)
    pub fn restart(&self) {
        self.shutdown();
        self.tx.send_replace(Status::Starting);
        self.launch();
    }

    fn launch(&self) {
        let tx = Arc::clone(&self.tx);
        if let Ok(url) = std::env::var("GEOSTAT_ENGINE_URL") {
            let token = std::env::var("GEOSTAT_ENGINE_TOKEN").unwrap_or_default();
            log::info!("외부 엔진 사용: {url}");
            tx.send_replace(Status::Ready(EngineInfo { url, token }));
            return;
        }
        let generation = {
            let mut g = self.generation.lock().unwrap();
            *g += 1;
            *g
        };

        let token = random_token();
        let mut child = match build_command(&self.app).and_then(|cmd| spawn(cmd, &token)) {
            Ok(child) => child,
            Err(err) => {
                log::error!("엔진 시작 실패: {err}");
                tx.send_replace(Status::Failed(err));
                return;
            }
        };

        let stdout = child
            .stdout
            .take()
            .expect("stdout 파이프가 설정돼 있어야 함");
        let stderr = child
            .stderr
            .take()
            .expect("stderr 파이프가 설정돼 있어야 함");
        let stderr_tail = Arc::new(Mutex::new(VecDeque::with_capacity(STDERR_TAIL_LINES)));

        // stderr: 로그로 넘기고 마지막 몇 줄은 실패 메시지용으로 보관함.
        // 파이프를 계속 비워야 엔진이 쓰기에서 막히지 않음
        {
            let tail = Arc::clone(&stderr_tail);
            thread::Builder::new()
                .name("engine-stderr".into())
                .spawn(move || {
                    for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                        eprintln!("[engine] {line}");
                        let mut t = tail.lock().unwrap();
                        if t.len() == STDERR_TAIL_LINES {
                            t.pop_front();
                        }
                        t.push_back(line);
                    }
                })
                .expect("stderr 스레드 생성 실패");
        }

        // stdout: 준비 신호를 찾아 상태를 Ready로 바꿈. EOF까지 계속 읽어 파이프를 비움
        {
            let tail = Arc::clone(&stderr_tail);
            let app = self.app.clone();
            let current = Arc::clone(&self.generation);
            thread::Builder::new()
                .name("engine-stdout".into())
                .spawn(move || {
                    let mut ready = false;
                    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                        if !ready {
                            if let Some(json) = line.strip_prefix(READY_PREFIX) {
                                match serde_json::from_str::<ReadyLine>(json) {
                                    Ok(r) => {
                                        ready = true;
                                        let url = format!("http://127.0.0.1:{}", r.port);
                                        log::info!("엔진 준비 완료: {url}");
                                        tx.send_replace(Status::Ready(EngineInfo {
                                            url,
                                            token: token.clone(),
                                        }));
                                    }
                                    Err(e) => {
                                        tx.send_replace(Status::Failed(format!(
                                            "엔진 준비 신호를 해석할 수 없음: {e}"
                                        )));
                                    }
                                }
                                continue;
                            }
                        }
                        println!("[engine] {line}");
                    }
                    if *current.lock().unwrap() != generation {
                        // 종료·재시작을 요청해서 끝난 이전 엔진임
                    } else if !ready {
                        let tail = tail.lock().unwrap();
                        let detail: Vec<&str> = tail.iter().map(String::as_str).collect();
                        tx.send_replace(Status::Failed(format!(
                            "엔진이 준비 전에 종료됨\n{}",
                            detail.join("\n")
                        )));
                    } else {
                        // 앱 종료·재시작 요청이 아닌데 끝났으면 비정상 종료로 보고 알림
                        let tail = tail.lock().unwrap();
                        let detail: Vec<&str> = tail
                            .iter()
                            .rev()
                            .take(8)
                            .rev()
                            .map(String::as_str)
                            .collect();
                        let message =
                            format!("분석 엔진이 예기치 않게 종료됨\n{}", detail.join("\n"));
                        log::error!("{message}");
                        tx.send_replace(Status::Failed(message.clone()));
                        let _ = app.emit(EXITED_EVENT, message);
                    }
                })
                .expect("stdout 스레드 생성 실패");
        }

        *self.child.lock().unwrap() = Some(child);
    }

    /// 엔진이 준비될 때까지 기다린 뒤 연결 정보를 반환함
    pub async fn info(&self) -> Result<EngineInfo, String> {
        let mut rx = self.status.clone();
        let waited = tokio::time::timeout(
            START_TIMEOUT,
            rx.wait_for(|s| !matches!(s, Status::Starting)),
        )
        .await;
        match waited {
            Ok(Ok(status)) => match &*status {
                Status::Ready(info) => Ok(info.clone()),
                Status::Failed(err) => Err(err.clone()),
                Status::Starting => unreachable!(),
            },
            Ok(Err(_)) => Err("엔진 상태 채널이 닫힘".into()),
            Err(_) => Err(format!(
                "엔진 시작 시간 초과 ({}초)",
                START_TIMEOUT.as_secs()
            )),
        }
    }

    /// 엔진을 종료함. stdin을 닫아 정상 종료를 유도하고, 응답이 없으면 강제 종료함
    pub fn shutdown(&self) {
        // 세대를 올려 두면 곧 끝날 이전 엔진의 stdout 스레드가 비정상 종료로 알리지 않음
        *self.generation.lock().unwrap() += 1;
        let Some(mut child) = self.child.lock().unwrap().take() else {
            return;
        };
        drop(child.stdin.take());
        let deadline = Instant::now() + SHUTDOWN_GRACE;
        while Instant::now() < deadline {
            if let Ok(Some(_)) = child.try_wait() {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        log::warn!("엔진이 제때 종료되지 않아 강제 종료함");
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn build_command(app: &AppHandle) -> Result<Command, String> {
    // 1. 개발 빌드: 저장소의 engine 프로젝트를 uv로 실행해 수정한 코드가 바로 반영되게 함.
    //    번들 엔진을 시험하려면 GEOSTAT_ENGINE_BUNDLED=1 을 지정함
    #[cfg(debug_assertions)]
    if std::env::var_os("GEOSTAT_ENGINE_BUNDLED").is_none() {
        if let Some(cmd) = dev_command()? {
            return Ok(cmd);
        }
    }

    // 2. 앱 번들에 포함된 엔진 (릴리스 빌드)
    if let Ok(resources) = app.path().resource_dir() {
        let exe = resources
            .join("engine")
            .join("geostat-engine")
            .join(exe_name("geostat-engine"));
        if exe.is_file() {
            log::info!("번들 엔진 사용: {}", exe.display());
            return Ok(Command::new(exe));
        }
    }

    Err("엔진 실행 파일을 찾을 수 없음".into())
}

#[cfg(debug_assertions)]
fn dev_command() -> Result<Option<Command>, String> {
    let engine_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../engine");
    if !engine_dir.join("pyproject.toml").is_file() {
        return Ok(None);
    }
    let uv = find_uv().ok_or_else(|| {
        "개발 모드 엔진 실행에 uv가 필요함 (https://docs.astral.sh/uv/)".to_string()
    })?;
    log::info!(
        "개발 엔진 사용: {} ({})",
        engine_dir.display(),
        uv.display()
    );
    let mut cmd = Command::new(uv);
    cmd.args(["run", "--quiet", "--project"])
        .arg(&engine_dir)
        .arg("geostat-engine");
    Ok(Some(cmd))
}

fn spawn(mut cmd: Command, token: &str) -> Result<Child, String> {
    // Windows: 엔진은 콘솔 프로그램이라 그냥 띄우면 검은 창이 뜨므로 창 없이 실행함
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd.arg("--exit-on-stdin-close")
        // 토큰은 명령줄 인수 대신 환경변수로 넘김 (ps로 노출되지 않게 함)
        .env("GEOSTAT_ENGINE_TOKEN", token)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    cmd.spawn()
        .map_err(|e| format!("엔진 프로세스를 실행하지 못함: {e}"))
}

fn exe_name(stem: &str) -> String {
    if cfg!(windows) {
        format!("{stem}.exe")
    } else {
        stem.to_string()
    }
}

/// Finder에서 실행한 앱은 셸 PATH를 물려받지 않으므로 흔한 설치 위치도 함께 찾음
#[cfg(debug_assertions)]
fn find_uv() -> Option<PathBuf> {
    if let Some(p) = std::env::var_os("GEOSTAT_UV") {
        return Some(PathBuf::from(p));
    }
    let mut candidates: Vec<PathBuf> = std::env::var_os("PATH")
        .map(|paths| {
            std::env::split_paths(&paths)
                .map(|d| d.join(exe_name("uv")))
                .collect()
        })
        .unwrap_or_default();
    if let Some(home) = std::env::var_os("HOME") {
        let home = PathBuf::from(home);
        candidates.push(home.join(".local/bin/uv"));
        candidates.push(home.join(".cargo/bin/uv"));
    }
    candidates.push(PathBuf::from("/opt/homebrew/bin/uv"));
    candidates.push(PathBuf::from("/usr/local/bin/uv"));
    candidates.into_iter().find(|p| p.is_file())
}

/// 256비트 임의 토큰 (16진수 64자)
fn random_token() -> String {
    let mut buf = [0u8; 32];
    getrandom::fill(&mut buf).expect("OS 난수 생성기를 쓸 수 없음");
    buf.iter().map(|b| format!("{b:02x}")).collect()
}
