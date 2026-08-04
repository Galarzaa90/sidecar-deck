from types import SimpleNamespace

from app import agent


class FakeProcess:
    def __init__(self, pid: int, name: str, create_time: float, user_time: float, system_time: float, rss_bytes: int) -> None:
        self.info = {
            "pid": pid,
            "name": name,
            "create_time": create_time,
            "cpu_times": SimpleNamespace(user=user_time, system=system_time),
            "memory_info": SimpleNamespace(rss=rss_bytes),
        }


def test_cpu_name_is_cached(monkeypatch) -> None:
    calls = 0

    def fake_windows_cpu_name() -> str:
        nonlocal calls
        calls += 1
        return "Example CPU"

    agent.cpu_name.cache_clear()
    monkeypatch.setattr(agent, "windows_cpu_name", fake_windows_cpu_name)

    assert agent.cpu_name() == "Example CPU"
    assert agent.cpu_name() == "Example CPU"
    assert calls == 1

    agent.cpu_name.cache_clear()


def test_top_processes_warms_then_reuses_one_combined_snapshot(monkeypatch) -> None:
    clock = 0.0
    snapshots = iter(
        [
            [
                FakeProcess(100, "chrome.exe", 1.0, 1.0, 0.0, 100),
                FakeProcess(101, "chrome.exe", 2.0, 2.0, 0.0, 50),
                FakeProcess(102, "MemCompression", 3.0, 1.0, 0.0, 1_000),
                FakeProcess(103, "System Idle Process", 4.0, 1.0, 0.0, 0),
            ],
            [
                FakeProcess(100, "chrome.exe", 1.0, 3.0, 0.0, 100),
                FakeProcess(101, "chrome.exe", 2.0, 3.0, 0.0, 50),
                FakeProcess(102, "MemCompression", 3.0, 3.0, 0.0, 1_000),
                FakeProcess(103, "System Idle Process", 4.0, 3.0, 0.0, 0),
            ],
            [
                FakeProcess(100, "chrome.exe", 1.0, 4.0, 0.0, 100),
                FakeProcess(101, "chrome.exe", 2.0, 4.0, 0.0, 50),
            ],
        ]
    )
    process_iter_calls: list[list[str]] = []

    monkeypatch.setattr(agent.time, "monotonic", lambda: clock)
    monkeypatch.setattr(agent.psutil, "cpu_count", lambda: 2)
    monkeypatch.setattr(agent, "TOP_PROCESS_POLL_SECONDS", 10)

    def fake_process_iter(attributes: list[str]):
        process_iter_calls.append(attributes)
        return next(snapshots)

    monkeypatch.setattr(agent.psutil, "process_iter", fake_process_iter)
    tracker = agent.RateTracker()

    first_cpu, first_memory = tracker.top_processes(total_memory=1_000)
    assert first_cpu == []
    assert [(item.name, item.pids, item.rssBytes, item.usagePercent) for item in first_memory] == [("chrome", [100, 101], 150, 15.0)]

    clock = 2.0
    second_cpu, second_memory = tracker.top_processes(total_memory=1_000)
    assert [(item.name, item.pids, item.usagePercent) for item in second_cpu] == [("chrome", [100, 101], 75.0)]
    assert second_memory == first_memory

    clock = 3.0
    cached_cpu, cached_memory = tracker.top_processes(total_memory=1_000)
    assert cached_cpu == second_cpu
    assert cached_memory == second_memory
    assert len(process_iter_calls) == 2

    clock = 12.1
    tracker.top_processes(total_memory=1_000)
    assert len(process_iter_calls) == 3
    assert process_iter_calls == [["pid", "name", "cpu_times", "create_time", "memory_info"]] * 3
