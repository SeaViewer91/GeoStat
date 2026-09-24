"""오래 걸리는 분석을 별도 프로세스에서 실행하는 작업 관리자.

엔진(HTTP 서버)이 계산 중에도 응답하도록 계산은 작업 프로세스에서 함.
- 진행률: 작업 프로세스가 큐로 (진행률, 메시지)를 보냄
- 취소: 작업 프로세스를 끝냄 (mgwr·spreg는 중간에 멈출 방법이 없어 프로세스 단위로 끊음)
- 결과: 작업 프로세스가 결과를 보내면 엔진 쪽에서 on_done으로 데이터셋에 반영함
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import threading
import time
import traceback
import uuid
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from geostat_engine.errors import EngineError, NotFound

log = logging.getLogger(__name__)

# 끝난 작업을 목록에 남겨 두는 시간 (초). 앱이 결과를 가져갈 시간을 줌
_KEEP_FINISHED = 600

# 엔진이 급히 종료될 때(os._exit) 작업 프로세스가 남지 않도록 모든 관리자를 기억해 둠
_MANAGERS: weakref.WeakSet[JobManager] = weakref.WeakSet()


def terminate_all() -> None:
    """실행 중인 모든 작업 프로세스를 끝냄 (엔진 종료 직전에 부름)."""
    for manager in list(_MANAGERS):
        manager.shutdown()


@dataclass
class Job:
    id: str
    kind: str
    title: str
    dataset_id: str
    status: str = "running"  # running · done · failed · cancelled
    progress: float | None = None
    message: str = "시작 중"
    started: float = field(default_factory=time.time)
    finished: float | None = None
    result: Any = None
    error: dict[str, str] | None = None
    _process: Any = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "dataset_id": self.dataset_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "elapsed": (self.finished or time.time()) - self.started,
            "result": self.result if self.status == "done" else None,
            "error": self.error,
        }


def _child_main(task: str, payload: dict[str, Any], out: Any) -> None:
    """작업 프로세스 진입점. task는 'regression' 같은 계산 종류임."""

    def progress(frac: float | None, message: str) -> None:
        out.put(("progress", frac, message))

    try:
        if task == "regression":
            from geostat_engine.analysis import regression

            result = regression.run(payload, progress)
        elif task == "cluster":
            from geostat_engine.analysis import cluster

            result = cluster.run(payload, progress)
        elif task == "zonal":
            from geostat_engine.analysis import zonal

            result = zonal.run(payload, progress)
        else:
            raise EngineError("invalid_task", f"알 수 없는 작업: {task}")
        out.put(("result", result))
    except EngineError as exc:
        out.put(("error", exc.code, exc.message))
    except MemoryError:
        out.put(("error", "out_of_memory", "메모리가 부족함. 관측치나 변수를 줄여야 함"))
    except Exception as exc:  # noqa: BLE001 - 계산 라이브러리 예외는 종류가 다양해 모두 전달함
        log.debug(traceback.format_exc())
        out.put(("error", "analysis_failed", f"{type(exc).__name__}: {exc}"))


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # spawn: 모든 OS에서 같은 방식으로 새 인터프리터를 띄움 (fork는 스레드와 함께 쓰면 위험함)
        self._ctx = mp.get_context("spawn")
        _MANAGERS.add(self)

    def start(
        self,
        task: str,
        payload: dict[str, Any],
        *,
        kind: str,
        title: str,
        dataset_id: str,
        on_done: Callable[[Any], Any],
    ) -> Job:
        job = Job(id=uuid.uuid4().hex[:10], kind=kind, title=title, dataset_id=dataset_id)
        out = self._ctx.Queue()
        proc = self._ctx.Process(target=_child_main, args=(task, payload, out), daemon=True)
        job._process = proc
        with self._lock:
            self._prune()
            self._jobs[job.id] = job
        proc.start()
        threading.Thread(
            target=self._watch, args=(job, proc, out, on_done), name=f"job-{job.id}", daemon=True
        ).start()
        return job

    def _watch(self, job: Job, proc: Any, out: Any, on_done: Callable[[Any], Any]) -> None:
        got_result = False
        while True:
            try:
                msg = out.get(timeout=0.2)
            except queue.Empty:
                if not proc.is_alive():
                    # 프로세스가 끝났는데 큐에 남은 메시지가 없으면 종료함
                    try:
                        msg = out.get(timeout=0.5)
                    except queue.Empty:
                        break
                else:
                    continue
            kind = msg[0]
            if kind == "progress":
                job.progress, job.message = msg[1], msg[2]
            elif kind == "result":
                got_result = True
                if job.status == "cancelled":
                    break
                try:
                    job.message = "결과 저장 중"
                    job.result = on_done(msg[1])
                    job.status = "done"
                    job.progress = 1.0
                    job.message = "완료"
                except EngineError as exc:
                    job.status, job.error = "failed", {"code": exc.code, "message": exc.message}
                except Exception as exc:
                    log.exception("작업 결과 반영 실패")
                    job.status = "failed"
                    job.error = {"code": "apply_failed", "message": f"{type(exc).__name__}: {exc}"}
                break
            elif kind == "error":
                job.status, job.error = "failed", {"code": msg[1], "message": msg[2]}
                break
        proc.join(timeout=5)
        # 큐가 쓰던 세마포어를 정리함 (남겨 두면 종료 시 경고가 뜸)
        out.close()
        out.join_thread()
        if job.status == "running" and not got_result:
            job.status = "failed"
            job.error = {
                "code": "worker_died",
                "message": f"작업 프로세스가 비정상 종료됨 (종료 코드 {proc.exitcode}). 메모리가 부족했을 수 있음",
            }
        job.finished = time.time()
        job._process = None

    def get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise NotFound("job_not_found", f"작업이 없음: {job_id}") from None

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.started)

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status == "running":
            job.status = "cancelled"
            job.message = "취소됨"
            proc = job._process
            if proc is not None and proc.is_alive():
                proc.terminate()
        return job

    def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            if job.status == "running":
                self.cancel(job.id)

    def _prune(self) -> None:
        now = time.time()
        for jid, j in list(self._jobs.items()):
            if j.finished and now - j.finished > _KEEP_FINISHED:
                del self._jobs[jid]
